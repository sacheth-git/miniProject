"""Why a job got its score: matched skills with resume evidence, gaps, breakdown."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.embeddings.encoder import get_encoder
from app.embeddings.faiss_index import get_index
from app.matching.scorer import Breakdown, Scorer
from app.matching.service import build_profile, get_scorer, job_features
from app.models.candidate import Candidate
from app.models.job import Job


def explain(db: Session, cand: Candidate, job: Job) -> dict[str, Any]:
    index = get_index()
    encoder = get_encoder()
    scorer = get_scorer()
    profile = build_profile(cand, encoder)
    feat = job_features([job], index, encoder)[0]
    bd = scorer.score(profile, feat, index.idf if index else {})
    return explanation_dict(bd, scorer)


def explanation_dict(bd: Breakdown, scorer: Scorer) -> dict[str, Any]:
    w = scorer.w
    reasons: list[str] = []
    if bd.matched:
        reasons.append("Matches " + ", ".join(m.name for m in bd.matched[:5]) + ".")
    if bd.missing_required:
        reasons.append("Missing required: " + ", ".join(m.name for m in bd.missing_required[:5]) + ".")
    weak = [k for k, v in bd.context_parts.items() if v < 0.6]
    if weak:
        reasons.append("Weaker fit on " + ", ".join(weak).replace("_", " ") + ".")
    reasons.append(f"Resume and job text are {'closely' if bd.sem >= 0.6 else 'moderately' if bd.sem >= 0.35 else 'loosely'} related.")
    return {
        **bd.to_dict(),
        "weights": vars(w),
        "contributions": {
            "semantic": round(w.alpha * bd.sem, 4),
            "skills": round(w.beta * bd.skill, 4),
            "context": round(w.gamma * bd.context, 4),
            "penalty": round(-w.delta * bd.penalty, 4),
        },
        "summary": " ".join(reasons),
    }
