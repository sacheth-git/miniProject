"""TPO analytics and recruiter share links, plus the public read-only share view."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.tpo_drives import _drive, _ranked_rows
from app.auth.deps import ensure_same_institution, tpo_user
from app.campus import analytics
from app.campus.export import COLUMNS, pick_columns
from app.core.db import get_db
from app.matching.service import IndexNotReady, MatchFilters, match
from app.models.campus import Drive
from app.models.candidate import Candidate
from app.models.share import ShareLink
from app.models.user import Institution, StudentProfile, User
from app.services.audit import audit

router = APIRouter(prefix="/tpo", tags=["tpo-analytics"])
public = APIRouter(tags=["share"])


@router.get("/analytics/summary")
def get_summary(user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    return analytics.summary(db, user.institution_id)  # type: ignore[arg-type]


@router.get("/analytics/skill-gap")
def get_skill_gap(top: int = Query(12, ge=3, le=30), user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    return analytics.skill_gap(db, user.institution_id, top)  # type: ignore[arg-type]


@router.get("/analytics/unplaced")
def get_unplaced(user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return analytics.unplaced(db, user.institution_id)  # type: ignore[arg-type]


@router.get("/analytics/unplaced/{student_user_id}/jobs")
def unplaced_jobs(student_user_id: str, limit: int = Query(3, ge=1, le=10), user: User = Depends(tpo_user),
                  db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Best-fit open-market jobs for one student (consent required)."""
    prof = db.scalars(select(StudentProfile).where(StudentProfile.user_id == student_user_id)).first()
    if prof is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    ensure_same_institution(user, prof.institution_id)
    if not prof.has_consent:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Student has not consented to share their profile")
    cand = db.scalars(select(Candidate).where(Candidate.user_id == student_user_id).order_by(Candidate.created_at.desc())).first()
    if cand is None:
        return []
    try:
        run = match(db, cand, MatchFilters(location="India"), limit=limit, persist=False, k=120)
    except IndexNotReady:
        return []
    return [{"job_id": it.job.id, "title": it.job.title, "company": it.job.company, "location": it.job.location,
             "match_percent": round(it.breakdown.score * 100), "apply_url": it.job.apply_url} for it in run.items]


@router.get("/analytics/fairness")
def get_fairness(user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    return analytics.fairness(db, user.institution_id)  # type: ignore[arg-type]


# ---------------- recruiter share links ----------------

class ShareIn(BaseModel):
    expires_in_days: int = Field(7, ge=1, le=60)
    blind: bool = True
    label: str = Field(default="", max_length=120)
    columns: list[str] | None = None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


@router.post("/drives/{drive_id}/share-link", status_code=status.HTTP_201_CREATED)
def create_share(drive_id: str, body: ShareIn, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _drive(db, user, drive_id)
    token = secrets.token_urlsafe(24)
    link = ShareLink(
        token_hash=_hash(token), token_hint=token[-6:], drive_id=d.id, institution_id=d.institution_id, created_by=user.id,
        label=body.label, blind=body.blind, columns=pick_columns(body.columns, body.blind),
        expires_at=datetime.now(timezone.utc) + timedelta(days=body.expires_in_days),
    )
    db.add(link)
    db.flush()
    audit(db, user, "share.create", "drive", d.id, after={"link_id": link.id, "blind": body.blind, "days": body.expires_in_days, "columns": link.columns})
    db.commit()
    # The token is returned once; only its hash is stored.
    return {**link.as_dict(), "token": token, "path": f"/share/{token}"}


@router.get("/drives/{drive_id}/share-links")
def list_shares(drive_id: str, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    d = _drive(db, user, drive_id)
    return [s.as_dict() for s in db.scalars(select(ShareLink).where(ShareLink.drive_id == d.id).order_by(ShareLink.id.desc()))]


@router.delete("/share-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(link_id: int, user: User = Depends(tpo_user), db: Session = Depends(get_db)) -> Response:
    link = db.get(ShareLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    ensure_same_institution(user, link.institution_id)
    link.revoked_at = datetime.now(timezone.utc)
    audit(db, user, "share.revoke", "drive", link.drive_id, after={"link_id": link.id})
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public.get("/share/{token}")
def view_share(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Public, read-only shortlist for a recruiter. No account needed; the link expires."""
    link = db.scalars(select(ShareLink).where(ShareLink.token_hash == _hash(token))).first()
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is not valid")
    if link.revoked_at is not None or (_aware(link.expires_at) or datetime.now(timezone.utc)) < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_410_GONE, "This link has expired or was revoked")
    d = db.get(Drive, link.drive_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Drive not found")
    rows = [r for r in _ranked_rows(db, d, link.blind) if r["shortlisted"]]
    cols = [c for c in link.columns if c in COLUMNS]
    link.views += 1
    link.last_viewed_at = datetime.now(timezone.utc)
    db.commit()
    inst = db.get(Institution, d.institution_id)
    return {
        "institution": inst.name if inst else "", "company": d.company, "role": d.role, "location": d.location,
        "ctc_lpa": d.ctc_lpa, "rounds": d.rounds or [], "blind": link.blind, "expires_at": link.expires_at,
        "columns": [{"key": c, "label": COLUMNS[c]} for c in cols],
        "rows": [{c: r.get(c) for c in cols} for r in rows],
    }
