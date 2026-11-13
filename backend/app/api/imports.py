"""User import: paste a JD, or upload your own job-alert emails (.eml)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.logging import get_logger
from app.ingestion.base import RawJob
from app.ingestion.normalizer import normalize
from app.ingestion.pipeline import apply_fields
from app.ingestion.user_import import parse_alert_email, raw_from_email_job, raw_from_text
from app.models.candidate import Candidate
from app.models.job import Job
from app.schemas.job import ImportResult, ImportTextIn
from app.skills.extractor import get_extractor

router = APIRouter(prefix="/import", tags=["import"])
log = get_logger(__name__)
MAX_FILES = 20


def _check_owner(db: Session, candidate_id: str | None) -> None:
    if candidate_id and db.get(Candidate, candidate_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")


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
def import_text(body: ImportTextIn, db: Session = Depends(get_db)) -> ImportResult:
    _check_owner(db, body.candidate_id)
    raw = raw_from_text(body.title, body.company, body.text, str(body.url) if body.url else None, body.location)
    created, updated, jobs = _save(db, [raw], body.candidate_id)
    return ImportResult(created=created, updated=updated, jobs=jobs)  # type: ignore[arg-type]


@router.post("/email", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def import_email(
    files: list[UploadFile] = File(..., description="Your own job-alert emails saved as .eml"),
    candidate_id: str | None = Form(None),
    db: Session = Depends(get_db),
) -> ImportResult:
    _check_owner(db, candidate_id)
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
    created, updated, jobs = await run_in_threadpool(_save, db, raws, candidate_id)
    log.info("Email import: %d created, %d updated, %d files skipped", created, updated, len(skipped))
    return ImportResult(created=created, updated=updated, jobs=jobs, skipped_files=skipped)  # type: ignore[arg-type]
