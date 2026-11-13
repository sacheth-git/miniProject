"""Deep-link search buttons for LinkedIn / Naukri / Indeed."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.candidate import Candidate
from app.services.deeplinks import build_deeplinks

router = APIRouter(prefix="/deeplinks", tags=["deeplinks"])


@router.get("/{candidate_id}")
def get_deeplinks(candidate_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    cand = db.get(Candidate, candidate_id)
    if cand is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    names = [s["name"] for s in sorted(cand.skills, key=lambda s: -s.get("confidence", 0))]
    return build_deeplinks(names, cand.preferences, cand.years_experience)
