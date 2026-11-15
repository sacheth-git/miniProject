"""Campus drives for TPOs: create/edit, eligibility, ranked shortlist, explanation, export.

The system recommends; the TPO decides. Every shortlist edit, rule change and
skill-weight change is written to the audit log. Gender, name, photo and college
are never used in scoring; blind mode hides name and email in the shortlist view.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import ensure_same_institution, tpo_user
from app.campus import export as exp
from app.campus.drives import StudentRecord, evaluate_drive, extract_drive_skills, rank_drive
from app.campus.lifecycle import notify_new_drive
from app.core.db import get_db
from app.eligibility.engine import reason_group, validate_custom_rule
from app.matching.explain import explanation_dict
from app.matching.service import get_scorer
from app.models.campus import DRIVE_CATEGORIES, DRIVE_STATUSES, DRIVE_TYPES, Drive, DriveApplication, EligibilityRule
from app.models.user import User
from app.parsing.pdf_parser import PDFParseError, extract_text
from app.services.audit import audit

router = APIRouter(prefix="/tpo/drives", tags=["tpo-drives"])

ETHICS_NOTE = (
    "SkillMatch recommends; the placement officer makes every shortlist decision. Scores never use name, "
    "gender, photo or college, and every manual change is recorded in the audit log."
)
SHORTLIST_STAGES = {"Shortlisted", "Test", "Interview", "Offer", "Accepted"}


# ---------------- schemas ----------------

class DriveSkill(BaseModel):
    skill_id: str
    name: str
    type: Literal["required", "preferred"]
    weight: float = Field(ge=0, le=5)
    evidence: str = ""


class RulesIn(BaseModel):
    allowed_branches: list[str] = Field(default_factory=list)
    batch_years: list[int] = Field(default_factory=list)
    min_cgpa: float | None = Field(default=None, ge=0, le=10)
    max_active_backlogs: int | None = Field(default=None, ge=0)
    max_history_backlogs: int | None = Field(default=None, ge=0)
    min_tenth: float | None = Field(default=None, ge=0, le=100)
    min_twelfth: float | None = Field(default=None, ge=0, le=100)
    custom_rules: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("custom_rules")
    @classmethod
    def _check(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for r in v:
            validate_custom_rule(r)
        return v


class DriveIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    job_type: Literal["internship", "fte", "intern+ppo"] = "fte"
    jd_text: str = Field(default="", max_length=50_000)
    ctc_lpa: float | None = Field(default=None, ge=0, le=500)
    stipend_month: float | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=200)
    rounds: list[str] = Field(default_factory=list)
    deadline: datetime | None = None
    status: Literal["draft", "open", "closed", "completed"] = "draft"
    category: Literal["regular", "dream"] = "regular"
    skills: list[DriveSkill] | None = None  # omitted: auto-extracted from the JD
    rules: RulesIn | None = None


class DrivePatch(BaseModel):
    company: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    job_type: Literal["internship", "fte", "intern+ppo"] | None = None
    jd_text: str | None = Field(default=None, max_length=50_000)
    ctc_lpa: float | None = Field(default=None, ge=0, le=500)
    stipend_month: float | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=200)
    rounds: list[str] | None = None
    deadline: datetime | None = None
    status: Literal["draft", "open", "closed", "completed"] | None = None
    category: Literal["regular", "dream"] | None = None
    skills: list[DriveSkill] | None = None
    reextract_skills: bool = False


class DriveOut(BaseModel):
    id: str
    company: str
    role: str
    job_type: str
    jd_text: str
    jd_filename: str | None
    skills: list[dict[str, Any]]
    ctc_lpa: float | None
    stipend_month: float | None
    location: str | None
    rounds: list[str]
    deadline: datetime | None
    status: str
    category: str
    rules: RulesIn
    created_at: datetime
    updated_at: datetime
    counts: dict[str, int] = Field(default_factory=dict)


class SelectIn(BaseModel):
    mode: Literal["top", "threshold", "manual"]
    n: int | None = Field(default=None, ge=1, le=2000)
    min_score: float | None = Field(default=None, ge=0, le=100, description="Match % threshold")
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)
    replace: bool = Field(default=False, description="top/threshold: also un-shortlist students outside the selection")


# ---------------- helpers ----------------

def _drive(db: Session, user: User, drive_id: str) -> Drive:
    d = db.get(Drive, drive_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Drive not found")
    ensure_same_institution(user, d.institution_id)
    return d


def _rules(db: Session, drive_id: str) -> EligibilityRule:
    r = db.scalars(select(EligibilityRule).where(EligibilityRule.drive_id == drive_id)).first()
    if r is None:
        r = EligibilityRule(drive_id=drive_id)
        db.add(r)
        db.flush()
    return r


def _rules_dict(r: EligibilityRule | None) -> dict[str, Any]:
    if r is None:
        return RulesIn().model_dump()
    return {k: getattr(r, k) for k in RulesIn.model_fields}


def _out(db: Session, d: Drive) -> DriveOut:
    r = db.scalars(select(EligibilityRule).where(EligibilityRule.drive_id == d.id)).first()
    apps = db.scalars(select(DriveApplication.stage).where(DriveApplication.drive_id == d.id)).all()
    counts = {"applied": sum(1 for s in apps if s != "Withdrawn"), "shortlisted": sum(1 for s in apps if s in SHORTLIST_STAGES)}
    return DriveOut(
        id=d.id, company=d.company, role=d.role, job_type=d.job_type, jd_text=d.jd_text, jd_filename=d.jd_filename,
        skills=d.skills or [], ctc_lpa=d.ctc_lpa, stipend_month=d.stipend_month, location=d.location,
        rounds=d.rounds or [], deadline=d.deadline, status=d.status, category=d.category,
        rules=RulesIn(**_rules_dict(r)), created_at=d.created_at, updated_at=d.updated_at, counts=counts,
    )


def _shortlist_row(rank: int | None, r: StudentRecord, blind: bool) -> dict[str, Any]:
    b = r.breakdown
    stage = r.application.stage if r.application else None
    return {
        "rank": rank,
        "user_id": r.user.id,
        "candidate_id": r.candidate.id if r.candidate else None,
        "roll_no": r.profile.roll_no,
        "name": None if blind else r.user.full_name,
        "email": None if blind else r.user.email,
        "branch": r.profile.branch,
        "batch_year": r.profile.batch_year,
        "cgpa": r.profile.cgpa,
        "match_percent": round(b.score * 100) if b else None,
        "skill_percent": round(b.skill * 100) if b else None,
        "matched_skills": [m.name for m in b.matched[:3]] if b else [],
        "missing_required": [m.name for m in b.missing_required] if b else [],
        "placed_status": r.profile.placed_status,
        "stage": stage,
        "applied": r.application is not None and r.application.source == "student",
        "shortlisted": stage in SHORTLIST_STAGES,
        "eligible": r.verdict.eligible,
        "reasons": r.verdict.reasons,
        "has_resume": r.candidate is not None,
    }


def _ranked_rows(db: Session, drive: Drive, blind: bool) -> list[dict[str, Any]]:
    recs = rank_drive(db, drive)
    rows, rank = [], 0
    for r in recs:
        if not r.verdict.eligible:
            continue
        if r.breakdown is not None:
            rank += 1
        rows.append(_shortlist_row(rank if r.breakdown is not None else None, r, blind))
    return rows


def _set_stage(db: Session, user: User, drive: Drive, uid: str, row: dict[str, Any] | None, shortlist: bool) -> bool:
    app = db.scalars(select(DriveApplication).where(DriveApplication.drive_id == drive.id, DriveApplication.student_id == uid)).first()
    now = datetime.now(timezone.utc).isoformat()
    before = app.stage if app else None
    if shortlist:
        if app is not None and app.stage in SHORTLIST_STAGES:
            return False
        snap = {"match_percent": row.get("match_percent"), "skill_percent": row.get("skill_percent"),
                "rank": row.get("rank")} if row else {}
        if app is None:
            app = DriveApplication(drive_id=drive.id, student_id=uid, source="tpo", stage="Shortlisted",
                                   match_snapshot=snap, stage_history=[{"stage": "Shortlisted", "at": now, "by": user.email}])
            db.add(app)
        else:
            app.stage = "Shortlisted"
            app.match_snapshot = app.match_snapshot or snap
            app.stage_history = [*(app.stage_history or []), {"stage": "Shortlisted", "at": now, "by": user.email}]
    else:
        if app is None or app.stage != "Shortlisted":
            return False  # later stages are moved in round tracking, not here
        if app.source == "tpo":
            db.delete(app)
        else:
            app.stage = "Applied"
            app.stage_history = [*(app.stage_history or []), {"stage": "Applied", "at": now, "by": user.email}]
    audit(db, user, "shortlist.add" if shortlist else "shortlist.remove", "drive", drive.id,
          before={"student_id": uid, "stage": before},
          after={"student_id": uid, "stage": "Shortlisted" if shortlist else ("removed" if app.source == "tpo" else "Applied"),
                 "match_percent": row.get("match_percent") if row else None})
    return True


# ---------------- routes ----------------

@router.post("/extract-jd")
async def extract_jd(
    file: UploadFile | None = File(None, description="JD as PDF or .txt"),
    text: str | None = Form(None),
    user: User = Depends(tpo_user),
) -> dict[str, Any]:
    """Preview: JD text (from upload or paste) and its auto-extracted skills with default weights."""
    if file is not None:
        data = await file.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "JD file larger than 5 MB")
        if data.startswith(b"%PDF"):
            try:
                text = extract_text(data).text
            except PDFParseError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        else:
            text = data.decode("utf-8", errors="replace")
    if not text or len(text.strip()) < 30:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide a JD file or at least 30 characters of text")
    return {"text": text, "skills": extract_drive_skills(text), "filename": file.filename if file else None}


@router.get("", response_model=list[DriveOut])
def list_drives(user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> list[DriveOut]:
    drives = db.scalars(select(Drive).where(Drive.institution_id == user.institution_id).order_by(Drive.created_at.desc())).all()
    return [_out(db, d) for d in drives]


@router.post("", response_model=DriveOut, status_code=status.HTTP_201_CREATED)
def create_drive(body: DriveIn, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> DriveOut:
    skills = [s.model_dump() for s in body.skills] if body.skills is not None else extract_drive_skills(body.jd_text) if body.jd_text else []
    d = Drive(
        institution_id=user.institution_id, created_by=user.id, skills=skills,
        **body.model_dump(exclude={"skills", "rules"}),
    )
    db.add(d)
    db.flush()
    r = _rules(db, d.id)
    for k, v in (body.rules or RulesIn()).model_dump().items():
        setattr(r, k, v)
    db.flush()
    if d.status == "open":
        notify_new_drive(db, d)
    audit(db, user, "drive.create", "drive", d.id, after={"company": d.company, "role": d.role, "skills": len(skills),
                                                         "rules": (body.rules or RulesIn()).model_dump()})
    db.commit()
    return _out(db, d)


@router.get("/{drive_id}", response_model=DriveOut)
def get_drive(drive_id: str, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> DriveOut:
    return _out(db, _drive(db, user, drive_id))


@router.put("/{drive_id}", response_model=DriveOut)
def update_drive(drive_id: str, body: DrivePatch, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> DriveOut:
    d = _drive(db, user, drive_id)
    changes = body.model_dump(exclude_unset=True, exclude={"skills", "reextract_skills"})
    before = {k: getattr(d, k) for k in changes}
    for k, v in changes.items():
        setattr(d, k, v)
    if changes:
        audit(db, user, "drive.update", "drive", d.id, before=_jsonable(before), after=_jsonable(changes))
    if changes.get("status") == "open" and before.get("status") != "open":
        db.flush()
        notify_new_drive(db, d)
    new_skills = None
    if body.skills is not None:
        new_skills = [s.model_dump() for s in body.skills]
    elif body.reextract_skills:
        new_skills = extract_drive_skills(d.jd_text)
    if new_skills is not None:
        audit(db, user, "drive.skills", "drive", d.id,
              before={"skills": [(s["name"], s["type"], s["weight"]) for s in d.skills or []]},
              after={"skills": [(s["name"], s["type"], s["weight"]) for s in new_skills]})
        d.skills = new_skills
    db.commit()
    return _out(db, d)


def _jsonable(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()}


@router.delete("/{drive_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_drive(drive_id: str, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> Response:
    d = _drive(db, user, drive_id)
    if d.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only draft drives can be deleted; close it instead")
    audit(db, user, "drive.delete", "drive", d.id, before={"company": d.company, "role": d.role})
    db.delete(d)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{drive_id}/eligibility")
def get_eligibility(drive_id: str, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _drive(db, user, drive_id)
    recs = evaluate_drive(db, d)
    def row(r: StudentRecord) -> dict[str, Any]:
        return {"user_id": r.user.id, "roll_no": r.profile.roll_no, "name": r.user.full_name, "branch": r.profile.branch,
                "batch_year": r.profile.batch_year, "cgpa": r.profile.cgpa, "placed_status": r.profile.placed_status,
                "has_resume": r.candidate is not None, "eligible": r.verdict.eligible, "reasons": r.verdict.reasons}
    rows = sorted((row(r) for r in recs), key=lambda x: (not x["eligible"], x["roll_no"] or ""))
    reasons: dict[str, int] = {}
    for r in recs:
        for key in {reason_group(x) for x in r.verdict.reasons}:
            reasons[key] = reasons.get(key, 0) + 1
    return {
        "rules": _rules_dict(db.scalars(select(EligibilityRule).where(EligibilityRule.drive_id == d.id)).first()),
        "total": len(rows), "eligible": sum(1 for r in rows if r["eligible"]),
        "reason_counts": dict(sorted(reasons.items(), key=lambda kv: -kv[1])), "students": rows,
    }


@router.put("/{drive_id}/eligibility")
def set_eligibility(drive_id: str, body: RulesIn, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _drive(db, user, drive_id)
    r = _rules(db, d.id)
    before = _rules_dict(r)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    audit(db, user, "drive.rules", "drive", d.id, before=before, after=body.model_dump())
    db.commit()
    return get_eligibility(drive_id, user, db)


@router.get("/{drive_id}/shortlist")
def get_shortlist(
    drive_id: str,
    blind: bool = Query(True, description="Hide name and email (default on for first-pass review)"),
    top: int | None = Query(None, ge=1),
    min_score: float | None = Query(None, ge=0, le=100),
    user: User = Depends(tpo_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    d = _drive(db, user, drive_id)
    rows = _ranked_rows(db, d, blind)
    if min_score is not None:
        rows = [r for r in rows if (r["match_percent"] or 0) >= min_score]
    if top is not None:
        rows = rows[:top]
    for r in rows:
        r.pop("candidate_id", None)
    return {"drive_id": d.id, "blind": blind, "note": ETHICS_NOTE, "rows": rows,
            "shortlisted": sum(1 for r in rows if r["shortlisted"])}


@router.post("/{drive_id}/shortlist")
def select_shortlist(drive_id: str, body: SelectIn, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _drive(db, user, drive_id)
    rows = _ranked_rows(db, d, blind=True)
    by_uid = {r["user_id"]: r for r in rows}  # eligible students only
    changed = 0
    if body.mode in ("top", "threshold"):
        scored = [r for r in rows if r["rank"] is not None]
        if body.mode == "top":
            if body.n is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "n is required for mode=top")
            chosen = scored[: body.n]
        else:
            if body.min_score is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "min_score is required for mode=threshold")
            chosen = [r for r in scored if r["match_percent"] >= body.min_score]
        chosen_ids = {r["user_id"] for r in chosen}
        for r in chosen:
            changed += _set_stage(db, user, d, r["user_id"], r, True)
        if body.replace:
            for r in rows:
                if r["shortlisted"] and r["user_id"] not in chosen_ids:
                    changed += _set_stage(db, user, d, r["user_id"], r, False)
    else:
        for uid in body.add:
            if uid not in by_uid:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Student {uid} is not eligible for this drive")
            changed += _set_stage(db, user, d, uid, by_uid[uid], True)
        for uid in body.remove:
            changed += _set_stage(db, user, d, uid, by_uid.get(uid), False)
    db.commit()
    return {"changed": changed, **get_shortlist(drive_id, True, None, None, user, db)}


@router.get("/{drive_id}/students/{student_user_id}/explain")
def explain_student(drive_id: str, student_user_id: str, blind: bool = True, user: User = Depends(tpo_user),
                    db: Session = Depends(get_db)) -> dict[str, Any]:
    """'Why ranked here': the same breakdown students see, plus eligibility."""
    d = _drive(db, user, drive_id)
    recs = rank_drive(db, d)
    rec = next((r for r in recs if r.user.id == student_user_id), None)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found in this institution")
    out: dict[str, Any] = {
        "user_id": rec.user.id, "roll_no": rec.profile.roll_no, "name": None if blind else rec.user.full_name,
        "eligible": rec.verdict.eligible, "reasons": rec.verdict.reasons, "has_resume": rec.candidate is not None,
        "rank": next((i + 1 for i, r in enumerate(x for x in recs if x.breakdown is not None) if r is rec), None),
    }
    if rec.breakdown is not None:
        out["explanation"] = explanation_dict(rec.breakdown, get_scorer())
    return out


@router.get("/{drive_id}/shortlist/export")
def export_shortlist(
    drive_id: str,
    format: Literal["xlsx", "csv", "pdf", "zip"] = "xlsx",
    blind: bool = False,
    scope: Literal["shortlisted", "ranked"] = "shortlisted",
    columns: str | None = Query(None, description=f"Comma-separated: {', '.join(exp.COLUMNS)}"),
    user: User = Depends(tpo_user),
    db: Session = Depends(get_db),
) -> Response:
    d = _drive(db, user, drive_id)
    rows = _ranked_rows(db, d, blind)
    if scope == "shortlisted":
        rows = [r for r in rows if r["shortlisted"]]
    if not rows:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing to export: shortlist students first (or use scope=ranked)")
    cols = exp.pick_columns(columns.split(",") if columns else None, blind)
    base = exp.safe_filename(f"{d.company}-{d.role}-{scope}")
    if format == "csv":
        data, media = exp.to_csv(rows, cols), "text/csv"
    elif format == "xlsx":
        data, media = exp.to_xlsx(rows, cols, d), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "pdf":
        data, media = exp.to_pdf(rows, cols, d, ETHICS_NOTE), "application/pdf"
    else:
        data, n = exp.to_resume_zip(rows, blind)
        if n == 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "No stored resume PDFs for these students")
        media = "application/zip"
    audit(db, user, "shortlist.export", "drive", d.id, after={"format": format, "scope": scope, "rows": len(rows), "blind": blind, "columns": cols})
    db.commit()
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{base}.{format}"'})


_ = (DRIVE_STATUSES, DRIVE_TYPES, DRIVE_CATEGORIES)  # documented enumerations used by the Literal types above
