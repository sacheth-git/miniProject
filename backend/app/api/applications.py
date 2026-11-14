"""Application tracker CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import SEEKER_ROLES, require_roles
from app.core.db import get_db
from app.models.application import STATUSES, Application
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.match import Match
from app.models.user import User

router = APIRouter(prefix="/applications", tags=["tracker"])
Status = Literal["Saved", "Ready", "Applied", "Interview", "Offer", "Rejected"]


class ApplicationIn(BaseModel):
    candidate_id: str
    job_id: str
    status: Status = "Saved"
    applied_via: str | None = Field(default=None, max_length=100, description="Publisher of the apply option used")
    apply_url: str | None = Field(default=None, max_length=2000)
    notes: str = Field(default="", max_length=5000)


class ApplicationPatch(BaseModel):
    status: Status | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: str
    job_id: str | None
    status: str
    title: str
    company: str
    location: str | None
    source: str
    apply_url: str
    applied_via: str | None
    match_score: float | None
    notes: str
    status_history: list[dict[str, str]]
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime
    job_active: bool = True


def _set_status(app: Application, new: str) -> None:
    if app.status == new and app.status_history:
        return
    now = datetime.now(timezone.utc)
    app.status = new
    app.status_history = [*(app.status_history or []), {"status": new, "at": now.isoformat()}]
    if new == "Applied" and app.applied_at is None:
        app.applied_at = now


Seeker = Depends(require_roles(*SEEKER_ROLES))


def _own_candidate(db: Session, user: User, candidate_id: str) -> Candidate:
    cand = db.get(Candidate, candidate_id)
    if cand is None or cand.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    return cand


def _own_app(db: Session, user: User, app_id: int) -> Application:
    app = db.get(Application, app_id)
    cand = db.get(Candidate, app.candidate_id) if app else None
    if app is None or cand is None or cand.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return app


def _out(db: Session, a: Application) -> ApplicationOut:
    out = ApplicationOut.model_validate(a)
    job = db.get(Job, a.job_id) if a.job_id else None
    out.job_active = bool(job and job.is_active)
    return out


@router.get("", response_model=list[ApplicationOut])
def list_applications(candidate_id: str = Query(...), user: User = Seeker, db: Session = Depends(get_db)) -> list[ApplicationOut]:
    _own_candidate(db, user, candidate_id)
    rows = db.scalars(
        select(Application).where(Application.candidate_id == candidate_id).order_by(Application.updated_at.desc())
    ).all()
    return [_out(db, a) for a in rows]


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def upsert_application(body: ApplicationIn, response: Response, user: User = Seeker, db: Session = Depends(get_db)) -> ApplicationOut:
    """Create, or move an existing entry for the same job to the new status."""
    _own_candidate(db, user, body.candidate_id)
    job = db.get(Job, body.job_id)
    if job is None or (job.owner_id is not None and job.owner_id != body.candidate_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    app = db.scalars(
        select(Application).where(Application.candidate_id == body.candidate_id, Application.job_id == body.job_id)
    ).first()
    if app is None:
        m = db.scalars(select(Match).where(Match.candidate_id == body.candidate_id, Match.job_id == body.job_id)).first()
        app = Application(
            candidate_id=body.candidate_id, job_id=job.id, title=job.title, company=job.company,
            location=job.location, source=job.source, apply_url=body.apply_url or job.apply_url,
            match_score=m.score if m else None, notes=body.notes, status_history=[],
        )
        db.add(app)
    else:
        response.status_code = status.HTTP_200_OK
        if body.notes:
            app.notes = body.notes
    if body.applied_via:
        app.applied_via = body.applied_via
    if body.apply_url:
        app.apply_url = body.apply_url
    _set_status(app, body.status)
    db.commit()
    db.refresh(app)
    return _out(db, app)


@router.patch("/{app_id}", response_model=ApplicationOut)
def update_application(app_id: int, body: ApplicationPatch, user: User = Seeker, db: Session = Depends(get_db)) -> ApplicationOut:
    app = _own_app(db, user, app_id)
    if body.status is not None:
        _set_status(app, body.status)
    if body.notes is not None:
        app.notes = body.notes
    db.commit()
    db.refresh(app)
    return _out(db, app)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(app_id: int, user: User = Seeker, db: Session = Depends(get_db)) -> Response:
    app = _own_app(db, user, app_id)
    db.delete(app)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/statuses", response_model=list[str])
def statuses() -> list[str]:
    return list(STATUSES)
