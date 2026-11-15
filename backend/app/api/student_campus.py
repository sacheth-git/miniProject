"""Student campus features: drives, apply/withdraw, offers, readiness, notifications, unified tracker.

Students see only their own scores. Peer ranks and other students' scores are never exposed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.deps import require_roles, student_profile_of
from app.campus import readiness as readiness_mod
from app.campus.drives import evaluate_drive, rank_drive
from app.campus.lifecycle import FINAL, apply, decide_offer, drive_stages, withdraw
from app.core.db import get_db
from app.matching.explain import explanation_dict
from app.matching.service import get_scorer
from app.models.application import Application
from app.models.campus import Drive, DriveApplication, Notification, Offer
from app.models.candidate import Candidate
from app.models.user import User

router = APIRouter(prefix="/student", tags=["student"])
Student = Depends(require_roles("student"))
Seeker = Depends(require_roles("student", "job_seeker"))


def _profile(db: Session, user: User):  # type: ignore[no-untyped-def]
    prof = student_profile_of(db, user)
    if prof is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Join your institution first")
    return prof


def _my_drive(db: Session, user: User, drive_id: str) -> Drive:
    prof = _profile(db, user)
    d = db.get(Drive, drive_id)
    if d is None or d.institution_id != prof.institution_id or d.status == "draft":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Drive not found")
    return d


def _drive_card(d: Drive, rec: Any, offer: Offer | None) -> dict[str, Any]:
    b = rec.breakdown if rec else None
    app = rec.application if rec else None
    deadline = d.deadline.replace(tzinfo=timezone.utc) if d.deadline and d.deadline.tzinfo is None else d.deadline
    return {
        "id": d.id, "company": d.company, "role": d.role, "job_type": d.job_type, "ctc_lpa": d.ctc_lpa,
        "stipend_month": d.stipend_month, "location": d.location, "category": d.category, "status": d.status,
        "deadline": deadline, "deadline_passed": bool(deadline and deadline < datetime.now(timezone.utc)),
        "rounds": d.rounds or [],
        "eligible": rec.verdict.eligible if rec else False, "reasons": rec.verdict.reasons if rec else [],
        "match_percent": round(b.score * 100) if b else None,
        "matched_skills": [m.name for m in b.matched[:4]] if b else [],
        "missing_required": [m.name for m in b.missing_required] if b else [],
        "missing_preferred": [m.name for m in b.missing_preferred] if b else [],
        "stage": app.stage if app else None,
        "applied": bool(app and app.source == "student" and app.stage != "Withdrawn"),
        "offer": {"id": offer.id, "ctc_lpa": offer.ctc_lpa, "status": offer.status} if offer else None,
    }


@router.get("/drives")
def my_drives(user: User = Student, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Open and in-progress drives of my institution: eligible first, ineligible with the exact reason."""
    prof = _profile(db, user)
    drives = db.scalars(select(Drive).where(Drive.institution_id == prof.institution_id, Drive.status != "draft").order_by(Drive.deadline)).all()
    offers = {o.drive_id: o for o in db.scalars(select(Offer).where(Offer.student_id == user.id))}
    out = []
    for d in drives:
        rec = next((r for r in evaluate_drive(db, d) if r.user.id == user.id), None)
        if rec is not None and rec.verdict.eligible:
            rank_drive(db, d, [rec])
        card = _drive_card(d, rec, offers.get(d.id))
        if d.status != "open" and not card["applied"] and not card["stage"]:
            continue  # closed drives only matter if I took part
        out.append(card)
    out.sort(key=lambda c: (not c["eligible"], c["deadline_passed"], -(c["match_percent"] or 0)))
    return out


@router.get("/drives/{drive_id}")
def my_drive(drive_id: str, user: User = Student, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _my_drive(db, user, drive_id)
    rec = next((r for r in evaluate_drive(db, d) if r.user.id == user.id), None)
    if rec is not None and rec.verdict.eligible:
        rank_drive(db, d, [rec])
    offer = db.scalars(select(Offer).where(Offer.drive_id == d.id, Offer.student_id == user.id)).first()
    card = _drive_card(d, rec, offer)
    card["jd_text"] = d.jd_text
    card["stages"] = [s for s in drive_stages(d) if s not in ("Rejected", "Withdrawn")]
    card["timeline"] = rec.application.stage_history if rec and rec.application else []
    card["explanation"] = explanation_dict(rec.breakdown, get_scorer()) if rec and rec.breakdown else None
    return card


@router.post("/drives/{drive_id}/apply")
def apply_drive(drive_id: str, user: User = Student, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _my_drive(db, user, drive_id)
    apply(db, user, d)
    db.commit()
    return my_drive(drive_id, user, db)


@router.post("/drives/{drive_id}/withdraw")
def withdraw_drive(drive_id: str, user: User = Student, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _my_drive(db, user, drive_id)
    withdraw(db, user, d)
    db.commit()
    return my_drive(drive_id, user, db)


@router.post("/offers/{offer_id}/{decision}")
def decide(offer_id: int, decision: str, user: User = Student, db: Session = Depends(get_db)) -> dict[str, Any]:
    if decision not in ("accept", "decline"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown decision")
    o = db.get(Offer, offer_id)
    if o is None or o.student_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    decide_offer(db, user, o, decision == "accept")
    db.commit()
    return my_drive(o.drive_id, user, db)


@router.get("/readiness")
def get_readiness(user: User = Student, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = readiness_mod.compute(db, user)
    return {"score": r.score, "match": r.match, "completeness": r.completeness, "ats": r.ats,
            "drives_considered": r.drives_considered, "checks": r.checks, "actions": r.actions,
            "weights": {"match": readiness_mod.W_MATCH, "completeness": readiness_mod.W_COMPLETE, "ats": readiness_mod.W_ATS}}


# ---------------- notifications (any student or job seeker) ----------------

@router.get("/notifications")
def notifications(unread_only: bool = False, limit: int = Query(30, ge=1, le=200), user: User = Seeker,
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    items = db.scalars(q.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).all()
    unread = len(db.scalars(select(Notification.id).where(Notification.user_id == user.id, Notification.read_at.is_(None))).all())
    return {"unread": unread, "items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
                                          "read": n.read_at is not None, "created_at": n.created_at} for n in items]}


@router.post("/notifications/read")
def mark_read(ids: list[int] | None = None, user: User = Seeker, db: Session = Depends(get_db)) -> dict[str, int]:
    q = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if ids:
        q = q.where(Notification.id.in_(ids))
    res = db.execute(q.values(read_at=datetime.now(timezone.utc)))
    db.commit()
    return {"marked": int(res.rowcount or 0)}  # type: ignore[attr-defined]


# ---------------- unified tracker ----------------

@router.get("/tracker")
def unified_tracker(user: User = Seeker, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Campus drive applications and open-market applications in one list, each with a source label."""
    out: list[dict[str, Any]] = []
    cand_ids = list(db.scalars(select(Candidate.id).where(Candidate.user_id == user.id)))
    for a in db.scalars(select(Application).where(Application.candidate_id.in_(cand_ids))):
        out.append({"kind": "open_market", "source_label": "Open market", "id": f"app-{a.id}", "title": a.title,
                    "company": a.company, "stage": a.status, "updated_at": a.updated_at, "link": f"/jobs?job={a.job_id}" if a.job_id else None,
                    "apply_url": a.apply_url, "final": a.status in ("Offer", "Rejected")})
    for app, d in db.execute(select(DriveApplication, Drive).join(Drive, Drive.id == DriveApplication.drive_id)
                             .where(DriveApplication.student_id == user.id)).all():
        if app.source != "student" and app.stage == "Shortlisted":
            continue  # TPO pre-shortlist the student hasn't acted on
        out.append({"kind": "campus", "source_label": "Campus drive", "id": f"drive-{app.id}", "title": d.role, "company": d.company,
                    "stage": app.stage, "updated_at": app.updated_at, "link": f"/campus/{d.id}", "apply_url": None,
                    "final": app.stage in FINAL})
    out.sort(key=lambda x: x["updated_at"], reverse=True)
    return out


def active_drive_applications(db: Session, user_id: str) -> int:
    return len([a for a in db.scalars(select(DriveApplication).where(DriveApplication.student_id == user_id))
                if a.stage not in FINAL and not (a.source == "tpo" and a.stage == "Shortlisted")])
