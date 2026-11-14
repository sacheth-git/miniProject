"""TPO (placement office) API. Every query is scoped to the TPO's own institution.

Phase 5A: institution details and the student roster (tenant isolation).
Phase 5B adds bulk import, drives, eligibility and shortlists.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import ensure_same_institution, tpo_user
from app.core.db import get_db
from app.models.candidate import Candidate
from app.models.user import Institution, StudentProfile, User

router = APIRouter(prefix="/tpo", tags=["tpo"])


class InstitutionOut(BaseModel):
    id: str
    name: str
    code: str
    invite_code: str
    settings: dict[str, object]


class StudentRow(BaseModel):
    user_id: str
    full_name: str
    email: str
    roll_no: str | None
    branch: str | None
    batch_year: int | None
    cgpa: float | None
    placed_status: str
    consent: bool
    has_resume: bool


class StudentDetail(StudentRow):
    active_backlogs: int
    history_backlogs: int
    tenth_pct: float | None
    twelfth_pct: float | None
    skills: list[str] | None  # None when consent is withdrawn
    consent_given_at: datetime | None


def _row(db: Session, user: User, prof: StudentProfile) -> dict[str, object]:
    has_resume = db.scalars(select(Candidate.id).where(Candidate.user_id == user.id)).first() is not None
    return {
        "user_id": user.id, "full_name": user.full_name, "email": user.email, "roll_no": prof.roll_no,
        "branch": prof.branch, "batch_year": prof.batch_year, "cgpa": prof.cgpa, "placed_status": prof.placed_status,
        "consent": prof.has_consent, "has_resume": has_resume,
    }


@router.get("/institution", response_model=InstitutionOut)
def my_institution(user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> Institution:
    inst = db.get(Institution, user.institution_id)
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Institution not found")
    return inst


@router.get("/students", response_model=list[StudentRow])
def list_students(user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.execute(
        select(User, StudentProfile)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(StudentProfile.institution_id == user.institution_id)  # tenant scope
        .order_by(StudentProfile.roll_no)
    ).all()
    return [_row(db, u, p) for u, p in rows]


@router.get("/students/{student_user_id}", response_model=StudentDetail)
def get_student(student_user_id: str, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, object]:
    prof = db.scalars(select(StudentProfile).where(StudentProfile.user_id == student_user_id)).first()
    if prof is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    ensure_same_institution(user, prof.institution_id)
    student = db.get(User, student_user_id)
    assert student is not None
    cand = db.scalars(select(Candidate).where(Candidate.user_id == student.id).order_by(Candidate.created_at.desc())).first()
    return {
        **_row(db, student, prof),
        "active_backlogs": prof.active_backlogs, "history_backlogs": prof.history_backlogs,
        "tenth_pct": prof.tenth_pct, "twelfth_pct": prof.twelfth_pct, "consent_given_at": prof.consent_given_at,
        # Resume-derived data only with consent.
        "skills": [s["name"] for s in cand.skills] if cand and prof.has_consent else None,
    }
