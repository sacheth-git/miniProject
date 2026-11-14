"""User import: paste a JD, or upload your own job-alert emails (.eml)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import SEEKER_ROLES, require_roles
from app.core.db import get_db
from app.core.logging import get_logger
from app.ingestion.base import RawJob
from app.ingestion.normalizer import normalize
from app.ingestion.pipeline import apply_fields
from app.ingestion.user_import import parse_alert_email, raw_from_email_job, raw_from_text
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.user import User
from app.schemas.job import ImportResult, ImportTextIn
from app.skills.extractor import get_extractor

router = APIRouter(prefix="/import", tags=["import"])
log = get_logger(__name__)
MAX_FILES = 20


def _owner_id(db: Session, user: User, candidate_id: str | None) -> str | None:
    """Imports belong to one of the user's resumes (the latest when none is named)."""
    if candidate_id:
        cand = db.get(Candidate, candidate_id)
        if cand is None or cand.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
        return cand.id
    return db.scalars(select(Candidate.id).where(Candidate.user_id == user.id).order_by(Candidate.created_at.desc())).first()


NO_RESUME = "Upload your resume first; imported jobs are scored against it"


def _save(db: Session, raws: list[RawJob], owner_id: str | None) -> tuple[int, int, list[Job]]:
    extractor = get_extractor()
    created = updated = 0
    jobs: list[Job] = []
    for raw in raws:
        n = normalize(raw)
        sid = f"{owner_id or 'anon'}:{n.source_job_id}"[:255]
        job = db.scalars(select(Job).where(Job.source == "import", Job.source_job_id == sid)).first()
        if job is None:
            job = Job(source="import", source_job_id=sid, owner_id=owner_id)
            db.add(job)
            created += 1
        else:
            updated += 1
        apply_fields(job, n, extractor)
        job.is_active = True
        jobs.append(job)
    db.commit()
    for j in jobs:
        db.refresh(j)
    return created, updated, jobs


@router.post("/text", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def import_text(body: ImportTextIn, user: User = Depends(require_roles(*SEEKER_ROLES)), db: Session = Depends(get_db)) -> ImportResult:
    owner = _owner_id(db, user, body.candidate_id)
    if owner is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_RESUME)
    raw = raw_from_text(body.title, body.company, body.text, str(body.url) if body.url else None, body.location)
    created, updated, jobs = _save(db, [raw], owner)
    return ImportResult(created=created, updated=updated, jobs=jobs)  # type: ignore[arg-type]


@router.post("/email", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def import_email(
    files: list[UploadFile] = File(..., description="Your own job-alert emails saved as .eml"),
    candidate_id: str | None = Form(None),
    user: User = Depends(require_roles(*SEEKER_ROLES)),
    db: Session = Depends(get_db),
) -> ImportResult:
    owner = _owner_id(db, user, candidate_id)
    if owner is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_RESUME)
    if len(files) > MAX_FILES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"At most {MAX_FILES} files per upload")
    raws: list[RawJob] = []
    skipped: list[str] = []
    for f in files:
        name = f.filename or "email.eml"
        data = await f.read(2 * 1024 * 1024 + 1)
        try:
            found = parse_alert_email(data)
        except ValueError as exc:
            skipped.append(f"{name}: {exc}")
            continue
        if not found:
            skipped.append(f"{name}: no job links found")
        raws.extend(raw_from_email_job(j) for j in found)
    created, updated, jobs = await run_in_threadpool(_save, db, raws, owner)
    log.info("Email import: %d created, %d updated, %d files skipped", created, updated, len(skipped))
    return ImportResult(created=created, updated=updated, jobs=jobs, skipped_files=skipped)  # type: ignore[arg-type]
