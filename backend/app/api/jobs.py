"""Job listing and detail."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.auth.deps import optional_user
from app.core.db import get_db
from app.models.candidate import Candidate
from app.models.user import User
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
    sort: Literal["mixed", "recent"] = Query("mixed", description="mixed: newest from each source in turn; recent: newest first"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> JobPage:
    """Public listing (guests can browse). Imported jobs appear only to their owner."""
    if candidate_id:
        cand = db.get(Candidate, candidate_id)
        if user is None or cand is None or cand.user_id != user.id:
            candidate_id = None
    stmt = apply_job_filters(
        select(Job), role=role, location=location, remote=remote, job_type=type, source=source,
        min_exp=min_exp, max_exp=max_exp, posted_within=posted_within, owner_id=candidate_id,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    newest = (Job.posted_at.desc().nulls_last(), Job.id)
    if sort == "mixed":
        # Round-robin across sources: the newest job of each source, then the second newest, and so on,
        # so one large feed does not bury the others.
        rn = func.row_number().over(partition_by=Job.source, order_by=newest).label("rn")
        ranked = stmt.with_only_columns(Job.id, rn).subquery()
        page = select(Job).join(ranked, Job.id == ranked.c.id).order_by(ranked.c.rn, *newest)
    else:
        page = stmt.order_by(*newest)
    rows = db.scalars(page.limit(limit).offset(offset)).all()
    return JobPage(total=total, limit=limit, offset=offset, items=rows)  # type: ignore[arg-type]


@router.get("/stats")
def job_stats(db: Session = Depends(get_db)) -> dict[str, object]:
    """Live counts for the landing page and source filter: totals by source, India, remote, internships."""
    base = apply_job_filters(select(Job))
    sub = base.subquery()
    count = lambda *conds: db.scalar(select(func.count()).select_from(sub).where(*conds)) or 0  # noqa: E731
    by_source = db.execute(select(sub.c.source, func.count()).group_by(sub.c.source).order_by(func.count().desc())).all()
    return {
        "total": count(),
        "india": count(sub.c.country.ilike("%india%")),
        "remote": count(sub.c.remote.is_(True)),
        "internships": count(sub.c.job_type == "internship"),
        "companies": db.scalar(select(func.count(func.distinct(sub.c.company)))) or 0,
        "by_source": [{"source": s, "count": n} for s, n in by_source],
    }


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if job.owner_id is not None:  # a private import
        owner = db.get(Candidate, job.owner_id)
        if user is None or owner is None or owner.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job
