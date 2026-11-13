"""Skill-gap advisor: which missing skills would raise the candidate's scores most."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.matching.service import MatchFilters, get_scorer, get_skill_space, match
from app.models.candidate import Candidate


def skill_gap(db: Session, cand: Candidate, filters: MatchFilters | None = None, top_n: int = 50, report: int = 5) -> dict[str, Any]:
    """Re-score the top jobs with each missing skill added; rank skills by gain."""
    run = match(db, cand, filters, limit=top_n, persist=False)
    scorer = get_scorer()
    space = get_skill_space()
    missing: dict[str, dict[str, Any]] = {}
    for it in run.items:
        for m in it.breakdown.missing_required + it.breakdown.missing_preferred:
            missing.setdefault(m.skill_id, {"skill_id": m.skill_id, "name": m.name})
    if not missing:
        return {"jobs_considered": len(run.items), "by_total_gain": [], "by_jobs_improved": []}
    cands = list(missing.values())
    vecs = space.vectors(cands)
    stats = []
    for s, v in zip(cands, vecs):
        gains = []
        for it in run.items:
            g = scorer.with_extra_skill(it.breakdown, v, s["skill_id"]) - it.breakdown.score
            if g > 0.005:
                gains.append((g, it.job))
        if not gains:
            continue
        total = sum(g for g, _ in gains)
        avg = total / len(gains)
        stats.append({
            "skill_id": s["skill_id"], "name": s["name"], "jobs_improved": len(gains),
            "avg_gain": round(avg, 4), "total_gain": round(total, 4),
            "message": f"Learn {s['name']}: +{avg * 100:.0f}% avg on {len(gains)} job{'s' if len(gains) != 1 else ''}",
            "example_jobs": [{"id": j.id, "title": j.title, "company": j.company} for _, j in sorted(gains, key=lambda x: -x[0])[:3]],
        })
    by_total = sorted(stats, key=lambda s: -s["total_gain"])[:report]
    by_count = sorted(stats, key=lambda s: (-s["jobs_improved"], -s["total_gain"]))[:report]
    return {"jobs_considered": len(run.items), "by_total_gain": by_total, "by_jobs_improved": by_count}
