"""TPO round tracking (Kanban, bulk moves, results CSV) and offers."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.tpo_drives import _drive
from app.auth.deps import ensure_same_institution, tpo_user
from app.campus.lifecycle import drive_stages, move_stage, record_offer
from app.core.db import get_db
from app.models.campus import Drive, DriveApplication, Offer
from app.models.user import StudentProfile, User
from app.services.audit import audit

router = APIRouter(prefix="/tpo", tags=["tpo-rounds"])


class MoveIn(BaseModel):
    student_ids: list[str] = Field(min_length=1, max_length=2000)
    stage: str
    note: str = Field(default="", max_length=500)


class OfferIn(BaseModel):
    drive_id: str
    student_id: str
    ctc_lpa: float | None = Field(default=None, gt=0, le=500)
    note: str = Field(default="", max_length=500)


class OfferPatch(BaseModel):
    status: Literal["accepted", "declined"]


class OfferOut(BaseModel):
    id: int
    drive_id: str
    company: str
    role: str
    student_id: str
    roll_no: str | None
    name: str
    branch: str | None
    ctc_lpa: float
    status: str
    note: str
    created_at: datetime
    decided_at: datetime | None


def _cards(db: Session, drive: Drive, blind: bool) -> list[dict[str, Any]]:
    rows = db.execute(
        select(DriveApplication, User, StudentProfile)
        .join(User, User.id == DriveApplication.student_id)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(DriveApplication.drive_id == drive.id)
    ).all()
    return [{
        "application_id": a.id, "student_id": u.id, "roll_no": p.roll_no, "name": None if blind else u.full_name,
        "branch": p.branch, "cgpa": p.cgpa, "stage": a.stage, "source": a.source,
        "match_percent": (a.match_snapshot or {}).get("match_percent"), "history": a.stage_history or [],
        "notes": a.tpo_notes,
    } for a, u, p in rows]


@router.get("/drives/{drive_id}/stages")
def get_stages(drive_id: str, blind: bool = False, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _drive(db, user, drive_id)
    cards = _cards(db, d, blind)
    stages = drive_stages(d)
    return {"stages": stages, "columns": {s: [c for c in cards if c["stage"] == s] for s in stages}}


@router.post("/drives/{drive_id}/stages")
def bulk_move(drive_id: str, body: MoveIn, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _drive(db, user, drive_id)
    apps = {a.student_id: a for a in db.scalars(select(DriveApplication).where(DriveApplication.drive_id == d.id))}
    missing = [s for s in body.student_ids if s not in apps]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{len(missing)} student(s) have no application in this drive")
    moved = sum(move_stage(db, user, d, apps[s], body.stage, body.note) for s in body.student_ids)
    db.commit()
    return {"moved": moved, **get_stages(drive_id, False, user, db)}


PASS = {"pass", "passed", "p", "yes", "y", "selected", "qualified", "cleared", "1", "true"}
FAIL = {"fail", "failed", "f", "no", "n", "rejected", "not selected", "0", "false"}


@router.post("/drives/{drive_id}/stages/results")
async def upload_results(
    drive_id: str,
    file: UploadFile = File(..., description="CSV with roll_no and result (pass/fail) columns"),
    round_name: str = Form(..., description="The round these results are for"),
    user: User = Depends(tpo_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Round results: students who passed move to the next round (or stay for an offer); the rest are rejected."""
    d = _drive(db, user, drive_id)
    stages = drive_stages(d)
    if round_name not in stages or round_name in {"Offer", "Accepted", "Rejected", "Withdrawn"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{round_name}' is not a round of this drive")
    nxt = stages[stages.index(round_name) + 1]
    raw = (await file.read(2 * 1024 * 1024)).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    fields = {re.sub(r"[\s\-.]+", "_", (f or "").strip().lower()): f for f in reader.fieldnames or []}
    roll_col = next((fields[k] for k in ("roll_no", "roll", "usn", "roll_number", "rollno") if k in fields), None)
    res_col = next((fields[k] for k in ("result", "status", "outcome", "passed") if k in fields), None)
    if roll_col is None or res_col is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "CSV needs 'roll_no' and 'result' columns")
    by_roll = {
        (p.roll_no or "").upper(): a
        for a, p in db.execute(
            select(DriveApplication, StudentProfile).join(StudentProfile, StudentProfile.user_id == DriveApplication.student_id)
            .where(DriveApplication.drive_id == d.id)
        ).all()
    }
    passed = failed = 0
    problems: list[str] = []
    for i, row in enumerate(reader, start=2):
        roll = (row.get(roll_col) or "").strip().upper()
        res = (row.get(res_col) or "").strip().lower()
        app = by_roll.get(roll)
        if app is None:
            problems.append(f"Line {i}: {roll or '(blank)'} has no application in this drive")
            continue
        if app.stage != round_name:
            problems.append(f"Line {i}: {roll} is at '{app.stage}', not '{round_name}'")
            continue
        if res in PASS:
            if nxt != "Offer":  # last round passed: wait for the offer to be recorded
                move_stage(db, user, d, app, nxt, f"Passed {round_name}")
            passed += 1
        elif res in FAIL:
            move_stage(db, user, d, app, "Rejected", f"Did not clear {round_name}")
            failed += 1
        else:
            problems.append(f"Line {i}: result '{res}' is not pass/fail")
    audit(db, user, "stage.results_upload", "drive", d.id, after={"round": round_name, "passed": passed, "failed": failed, "problems": len(problems)})
    db.commit()
    return {"round": round_name, "next_stage": nxt, "passed": passed, "failed": failed, "problems": problems}


# ---------------- offers ----------------

def _offer_out(db: Session, o: Offer) -> OfferOut:
    d = db.get(Drive, o.drive_id)
    u = db.get(User, o.student_id)
    p = db.scalars(select(StudentProfile).where(StudentProfile.user_id == o.student_id)).first()
    return OfferOut(
        id=o.id, drive_id=o.drive_id, company=d.company if d else "", role=d.role if d else "", student_id=o.student_id,
        roll_no=p.roll_no if p else None, name=u.full_name if u else "", branch=p.branch if p else None, ctc_lpa=o.ctc_lpa,
        status=o.status, note=o.note, created_at=o.created_at, decided_at=o.decided_at,
    )


@router.get("/offers", response_model=list[OfferOut])
def list_offers(drive_id: str | None = None, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> list[OfferOut]:
    q = select(Offer).where(Offer.institution_id == user.institution_id)
    if drive_id:
        q = q.where(Offer.drive_id == drive_id)
    return [_offer_out(db, o) for o in db.scalars(q.order_by(Offer.created_at.desc()))]


@router.post("/offers", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
def create_offer(body: OfferIn, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> OfferOut:
    d = _drive(db, user, body.drive_id)
    o = record_offer(db, user, d, body.student_id, body.ctc_lpa, body.note)
    db.commit()
    return _offer_out(db, o)


@router.patch("/offers/{offer_id}", response_model=OfferOut)
def record_decision(offer_id: int, body: OfferPatch, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> OfferOut:
    """Record a decision the student communicated offline (same rules as the student accepting in-app)."""
    from app.campus.lifecycle import decide_offer

    o = db.get(Offer, offer_id)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    ensure_same_institution(user, o.institution_id)
    student = db.get(User, o.student_id)
    assert student is not None
    decide_offer(db, student, o, body.status == "accepted")
    audit(db, user, "offer.recorded_decision", "offer", str(o.id), after={"status": body.status})
    db.commit()
    return _offer_out(db, o)
