"""Deep-link search buttons for LinkedIn / Naukri / Indeed."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth.deps import owned_candidate
from app.models.candidate import Candidate
from app.services.deeplinks import build_deeplinks

router = APIRouter(prefix="/deeplinks", tags=["deeplinks"])


@router.get("/{candidate_id}")
def get_deeplinks(candidate_id: str, cand: Candidate = Depends(owned_candidate)) -> dict[str, Any]:
    names = [s["name"] for s in sorted(cand.skills, key=lambda s: -s.get("confidence", 0))]
    return build_deeplinks(names, cand.preferences, cand.years_experience)
