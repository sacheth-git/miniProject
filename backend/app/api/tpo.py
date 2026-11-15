"""TPO (placement office) API: institution, students, bulk import, policy, audit log.

Every query is scoped to the TPO's own institution; direct access to another
institution's records returns 403. Drives live in app/api/tpo_drives.py.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import ensure_same_institution, tpo_user
from app.campus import bulk_import
from app.core.db import get_db
from app.models.campus import AuditLog, ImportJob
from app.models.candidate import Candidate
from app.models.user import DEFAULT_POLICY, Institution, StudentProfile, User
from app.services.audit import audit

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
    active_backlogs: int = 0
    placed_status: str
    consent: bool
    consent_status: str
    has_resume: bool
    must_reset_password: bool = False


class StudentDetail(StudentRow):
    history_backlogs: int
    tenth_pct: float | None
    twelfth_pct: float | None
    diploma_pct: float | None
    current_best_offer_ctc: float | None
    skills: list[str] | None  # None without consent
    years_experience: float | None
    consent_given_at: datetime | None


class PolicyIn(BaseModel):
    one_offer_rule: bool = True
    dream_multiplier: float = Field(1.5, ge=1.0, le=5.0)
    block_after_accept: bool = True


def consent_status(p: StudentProfile) -> str:
    if p.has_consent:
        return "given"
    return "withdrawn" if p.consent_withdrawn_at else "pending"


def _row(user: User, prof: StudentProfile, has_resume: bool) -> dict[str, Any]:
    return {
        "user_id": user.id, "full_name": user.full_name, "email": user.email, "roll_no": prof.roll_no,
        "branch": prof.branch, "batch_year": prof.batch_year, "cgpa": prof.cgpa, "active_backlogs": prof.active_backlogs,
        "placed_status": prof.placed_status, "consent": prof.has_consent, "consent_status": consent_status(prof),
        "has_resume": has_resume, "must_reset_password": user.must_reset_password,
    }


# ---------------- institution & policy ----------------

@router.get("/institution", response_model=InstitutionOut)
def my_institution(user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> Institution:
    inst = db.get(Institution, user.institution_id)
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Institution not found")
    return inst


@router.get("/settings/policy", response_model=PolicyIn)
def get_policy(user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    inst = db.get(Institution, user.institution_id)
    return {**DEFAULT_POLICY, **((inst.settings if inst else None) or {})}


@router.put("/settings/policy", response_model=PolicyIn)
def set_policy(body: PolicyIn, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    inst = db.get(Institution, user.institution_id)
    assert inst is not None
    before = {**DEFAULT_POLICY, **(inst.settings or {})}
    inst.settings = {**(inst.settings or {}), **body.model_dump()}
    audit(db, user, "policy.update", "institution", inst.id, before=before, after=body.model_dump())
    db.commit()
    return inst.settings


# ---------------- students ----------------

@router.get("/students", response_model=list[StudentRow])
def list_students(user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(
        select(User, StudentProfile)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(StudentProfile.institution_id == user.institution_id)  # tenant scope
        .order_by(StudentProfile.roll_no)
    ).all()
    with_resume = set(db.scalars(select(Candidate.user_id).where(Candidate.user_id.in_([u.id for u, _ in rows]))))
    return [_row(u, p, u.id in with_resume) for u, p in rows]


@router.get("/students/{student_user_id}", response_model=StudentDetail)
def get_student(student_user_id: str, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    prof = db.scalars(select(StudentProfile).where(StudentProfile.user_id == student_user_id)).first()
    if prof is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    ensure_same_institution(user, prof.institution_id)
    student = db.get(User, student_user_id)
    assert student is not None
    cand = db.scalars(select(Candidate).where(Candidate.user_id == student.id).order_by(Candidate.created_at.desc())).first()
    ok = prof.has_consent
    return {
        **_row(student, prof, cand is not None),
        "history_backlogs": prof.history_backlogs, "tenth_pct": prof.tenth_pct, "twelfth_pct": prof.twelfth_pct,
        "diploma_pct": prof.diploma_pct, "current_best_offer_ctc": prof.current_best_offer_ctc,
        "consent_given_at": prof.consent_given_at,
        # Resume-derived data only with consent.
        "skills": [s["name"] for s in cand.skills] if cand and ok else None,
        "years_experience": cand.years_experience if cand and ok else None,
    }


# ---------------- bulk import ----------------

class ImportPreview(BaseModel):
    job_id: str
    total: int
    ok: int
    warnings: int
    errors: int
    creates: int
    updates: int
    with_resume: int
    rows: list[dict[str, Any]]


class ImportStatus(BaseModel):
    job_id: str
    status: str
    total: int
    done: int
    created: int
    updated: int
    resumes_parsed: int
    errors: list[dict[str, Any]]
    message: str
    credentials_available: bool


def _job(db: Session, user: User, job_id: str) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    ensure_same_institution(user, job.institution_id)
    return job


@router.post("/students/import/preview", response_model=ImportPreview)
async def import_preview(
    csv_file: UploadFile = File(..., description="roll_no,name,email,branch,batch,cgpa,active_backlogs,tenth,twelfth"),
    resumes_zip: UploadFile | None = File(None, description="ZIP of {roll_no}.pdf"),
    user: User = Depends(tpo_user),
    db: Session = Depends(get_db),
) -> ImportPreview:
    csv_bytes = await csv_file.read(bulk_import.MAX_CSV_BYTES + 1)
    zip_bytes = await resumes_zip.read(bulk_import.MAX_ZIP_BYTES + 1) if resumes_zip else None
    try:
        rows = bulk_import.parse_preview(csv_bytes, zip_bytes, db, user.institution_id)  # type: ignore[arg-type]
    except bulk_import.BulkImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    job = ImportJob(institution_id=user.institution_id, created_by=user.id, status="preview", total=len(rows), rows=rows)
    db.add(job)
    db.commit()
    bulk_import.store_upload(job.id, csv_bytes, zip_bytes)
    count = lambda s: sum(1 for r in rows if r["status"] == s)  # noqa: E731
    valid = [r for r in rows if r["status"] != "error"]
    return ImportPreview(
        job_id=job.id, total=len(rows), ok=count("ok"), warnings=count("warning"), errors=count("error"),
        creates=sum(1 for r in valid if r["action"] == "create"), updates=sum(1 for r in valid if r["action"] == "update"),
        with_resume=sum(1 for r in valid if r["has_resume"]), rows=rows,
    )


@router.post("/students/import/{job_id}/commit", response_model=ImportStatus, status_code=status.HTTP_202_ACCEPTED)
def import_commit(job_id: str, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> ImportStatus:
    job = _job(db, user, job_id)
    if job.status != "preview":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Import already {job.status}")
    if not any(r["status"] != "error" for r in job.rows):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Every row has errors; fix the CSV and preview again")
    job.status = "running"
    db.commit()
    bulk_import.start_commit(job.id, user.id)
    return _status(job)


def _status(job: ImportJob) -> ImportStatus:
    return ImportStatus(
        job_id=job.id, status=job.status, total=job.total, done=job.done, created=job.created, updated=job.updated,
        resumes_parsed=job.resumes_parsed, errors=job.errors, message=job.message,
        credentials_available=bool(job.credentials),
    )


@router.get("/students/import/{job_id}", response_model=ImportStatus)
def import_status(job_id: str, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> ImportStatus:
    return _status(_job(db, user, job_id))


@router.get("/students/import/{job_id}/credentials")
def import_credentials(job_id: str, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> Response:
    """Temporary passwords for new accounts, as CSV. Available once, then wiped."""
    job = _job(db, user, job_id)
    if not job.credentials:
        raise HTTPException(status.HTTP_410_GONE, "Credentials were already downloaded (or none were created)")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["roll_no", "name", "email", "temporary_password"])
    w.writeheader()
    w.writerows(job.credentials)
    job.credentials = None
    audit(db, user, "students.credentials_downloaded", "import_job", job.id)
    db.commit()
    return Response(
        buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="student-logins-{job.id[:8]}.csv"'},
    )


# ---------------- audit log ----------------

class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_email: str
    action: str
    entity: str
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    at: datetime


class AuditPage(BaseModel):
    total: int
    items: list[AuditOut]


@router.get("/audit", response_model=AuditPage)
def audit_log(
    action: str | None = Query(None, description="Prefix, e.g. 'shortlist'"),
    entity: str | None = None,
    entity_id: str | None = None,
    actor: str | None = Query(None, description="Actor email contains"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(tpo_user),
    db: Session = Depends(get_db),
) -> AuditPage:
    q = select(AuditLog).where(AuditLog.institution_id == user.institution_id)
    if action:
        q = q.where(AuditLog.action.startswith(action))
    if entity:
        q = q.where(AuditLog.entity == entity)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if actor:
        q = q.where(AuditLog.actor_email.ilike(f"%{actor}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = db.scalars(q.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).all()
    return AuditPage(total=total, items=items)  # type: ignore[arg-type]
