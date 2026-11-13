"""Job listing and detail."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.db import get_db
from app.models.job import Job
from app.schemas.job import JobDetail, JobPage

router = APIRouter(prefix="/jobs", tags=["jobs"])

JOB_TYPES = {"internship", "full-time", "contract", "part-time"}


def apply_job_filters(
    stmt: Select,  # type: ignore[type-arg]
    *,
    role: str | None = None,
    location: str | None = None,
    remote: bool | None = None,
    job_type: str | None = None,
    source: str | None = None,
    min_exp: float | None = None,
    max_exp: float | None = None,
    posted_within: int | None = None,
    owner_id: str | None = None,
) -> Select:  # type: ignore[type-arg]
    """Shared by /jobs and /match: active, canonical, public-or-own jobs plus user filters."""
    stmt = stmt.where(Job.is_active.is_(True), Job.is_duplicate.is_(False))
    stmt = stmt.where(or_(Job.owner_id.is_(None), Job.owner_id == owner_id) if owner_id else Job.owner_id.is_(None))
    if role:
        for word in role.split():
            stmt = stmt.where(Job.title.ilike(f"%{word}%"))
    if location:
        like = f"%{location}%"
        stmt = stmt.where(or_(Job.location.ilike(like), Job.country.ilike(like)))
    if remote is not None:
        stmt = stmt.where(Job.remote.is_(remote))
    if job_type:
        types = [t.strip() for t in job_type.split(",") if t.strip()]
        bad = set(types) - JOB_TYPES
        if bad:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown job type(s): {sorted(bad)}")
        stmt = stmt.where(Job.job_type.in_(types))
    if source:
        stmt = stmt.where(Job.source.in_([s.strip() for s in source.split(",") if s.strip()]))
    # Experience filter: the job's range must overlap the requested range.
    if min_exp is not None:
        stmt = stmt.where(or_(Job.experience_max.is_(None), Job.experience_max >= min_exp))
    if max_exp is not None:
        stmt = stmt.where(or_(Job.experience_min.is_(None), Job.experience_min <= max_exp))
    if posted_within:
        since = datetime.now(timezone.utc) - timedelta(days=posted_within)
        stmt = stmt.where(or_(Job.posted_at >= since, Job.posted_at.is_(None) & (Job.first_seen_at >= since)))
    return stmt


@router.get("", response_model=JobPage)
def list_jobs(
    role: str | None = Query(None, description="Words that must appear in the title"),
    location: str | None = Query(None, description="City or country substring"),
    remote: bool | None = None,
    type: str | None = Query(None, description="internship, full-time, contract, part-time (comma-separated)"),
    source: str | None = Query(None, description="Comma-separated source names"),
    min_exp: float | None = Query(None, ge=0),
    max_exp: float | None = Query(None, ge=0),
    posted_within: int | None = Query(None, ge=1, le=365, description="Days"),
    candidate_id: str | None = Query(None, description="Include this candidate's imported jobs"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> JobPage:
    stmt = apply_job_filters(
        select(Job), role=role, location=location, remote=remote, job_type=type, source=source,
        min_exp=min_exp, max_exp=max_exp, posted_within=posted_within, owner_id=candidate_id,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Job.posted_at.desc().nulls_last(), Job.id).limit(limit).offset(offset)).all()
    return JobPage(total=total, limit=limit, offset=offset, items=rows)  # type: ignore[arg-type]


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: str, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job
