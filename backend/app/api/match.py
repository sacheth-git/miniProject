"""Ranked matches, per-job explanation, and skill-gap advice."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import owned_candidate
from app.core.db import get_db
from app.matching.baselines import METHODS
from app.matching.explain import explain
from app.matching.gap_advisor import skill_gap
from app.matching.service import IndexNotReady, MatchFilters, match
from app.models.candidate import Candidate
from app.models.job import Job
from app.schemas.match import ExplainResponse, GapResponse, MatchItem, MatchResponse

router = APIRouter(tags=["match"])


def filters_dep(
    role: str | None = Query(None),
    location: str | None = Query(None),
    remote: bool | None = None,
    type: str | None = Query(None, description="internship, full-time, contract, part-time"),
    source: str | None = None,
    min_exp: float | None = Query(None, ge=0),
    max_exp: float | None = Query(None, ge=0),
    posted_within: int | None = Query(None, ge=1, le=365),
) -> MatchFilters:
    return MatchFilters(role, location, remote, type, source, min_exp, max_exp, posted_within)


def _index_error(exc: IndexNotReady) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.get("/match/{candidate_id}", response_model=MatchResponse)
def get_matches(
    candidate_id: str,
    filters: MatchFilters = Depends(filters_dep),
    limit: int = Query(20, ge=1, le=100),
    method: str = Query("ours", description=f"Ranking method: {', '.join(METHODS)}"),
    cand: Candidate = Depends(owned_candidate),
    db: Session = Depends(get_db),
) -> MatchResponse:
    if method not in METHODS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"method must be one of {METHODS}")
    try:
        run = match(db, cand, filters, limit=limit, method=method)
    except IndexNotReady as exc:
        raise _index_error(exc) from exc
    items: list[MatchItem] = []
    for rank, it in enumerate(run.items, 1):
        b = it.breakdown
        items.append(
            MatchItem.model_validate(
                {
                    "rank": rank,
                    "match_percent": round(b.score * 100),
                    "method_score": round(it.method_score, 4),
                    "job": it.job,
                    "breakdown": b.to_dict(),
                    "matched_skills": [vars(m) for m in b.matched],
                    "missing_required": [vars(m) for m in b.missing_required],
                    "missing_preferred": [vars(m) for m in b.missing_preferred],
                },
                from_attributes=True,
            )
        )
    return MatchResponse(
        candidate_id=candidate_id, method=method, retrieved=run.retrieved, returned=len(items),
        timings_ms=run.timings_ms, items=items,
    )


@router.get("/match/{candidate_id}/{job_id}/explain", response_model=ExplainResponse)
def explain_match(
    candidate_id: str, job_id: str, cand: Candidate = Depends(owned_candidate), db: Session = Depends(get_db)
) -> dict[str, Any]:
    job = db.get(Job, job_id)
    if job is None or (job.owner_id is not None and job.owner_id != candidate_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return explain(db, cand, job)


@router.get("/gap/{candidate_id}", response_model=GapResponse)
def get_gap(
    candidate_id: str,
    filters: MatchFilters = Depends(filters_dep),
    top_n: int = Query(50, ge=5, le=200),
    cand: Candidate = Depends(owned_candidate),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return skill_gap(db, cand, filters, top_n=top_n)
    except IndexNotReady as exc:
        raise _index_error(exc) from exc
