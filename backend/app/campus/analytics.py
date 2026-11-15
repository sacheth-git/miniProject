"""Placement analytics for a TPO: KPIs, funnel, skill-gap heatmap, unplaced students, fairness.

Privacy: resume-derived data (skills, matches) only for students who consented. Gender is
used only for aggregate fairness numbers, and groups smaller than MIN_GROUP are suppressed.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.campus.drives import StudentRecord, evaluate_drive, in_drive, institution_students, is_shortlisted, rank_drive
from app.matching.calibration import calibration_for
from app.matching.scorer import SKILL_MATCH_THRESHOLD
from app.matching.service import get_skill_space
from app.models.campus import Drive, DriveApplication, Offer
from app.models.user import StudentProfile

MIN_GROUP = 10


def _ever_shortlisted(app: DriveApplication) -> bool:
    return is_shortlisted(app) or any(h.get("stage") == "Shortlisted" for h in app.stage_history or [])


def _active_drives(db: Session, inst: str) -> list[Drive]:
    return list(db.scalars(select(Drive).where(Drive.institution_id == inst, Drive.status != "draft")))


# ---------------- KPIs and funnel ----------------

def summary(db: Session, inst: str) -> dict[str, Any]:
    profiles = db.scalars(select(StudentProfile).where(StudentProfile.institution_id == inst)).all()
    offers = db.scalars(select(Offer).where(Offer.institution_id == inst)).all()
    drives = _active_drives(db, inst)
    accepted = [o for o in offers if o.status == "accepted"]
    ctcs = sorted(o.ctc_lpa for o in accepted)

    def group(key: str) -> list[dict[str, Any]]:
        g: dict[Any, list[StudentProfile]] = defaultdict(list)
        for p in profiles:
            g[getattr(p, key) or "Unknown"].append(p)
        rows = []
        for k, ps in sorted(g.items(), key=lambda kv: str(kv[0])):
            placed = sum(p.placed_status == "placed" for p in ps)
            rows.append({key: k, "students": len(ps), "placed": placed, "offered": sum(p.placed_status == "offered" for p in ps),
                         "placed_pct": round(100 * placed / len(ps), 1) if ps else 0.0})
        return rows

    by_company: dict[str, dict[str, Any]] = {}
    drive_by_id = {d.id: d for d in drives}
    for o in offers:
        d = drive_by_id.get(o.drive_id)
        if d is None:
            continue
        c = by_company.setdefault(d.company, {"company": d.company, "offers": 0, "accepted": 0, "ctc": []})
        c["offers"] += o.status != "declined"
        c["accepted"] += o.status == "accepted"
        c["ctc"].append(o.ctc_lpa)
    companies = [{**{k: v for k, v in c.items() if k != "ctc"}, "avg_ctc": round(statistics.mean(c["ctc"]), 2)}
                 for c in sorted(by_company.values(), key=lambda c: -c["offers"])]

    funnel_rows = []
    totals = Counter()
    for d in sorted(drives, key=lambda d: d.created_at):
        recs = evaluate_drive(db, d)
        apps = [r.application for r in recs if r.application is not None]
        row = {
            "drive_id": d.id, "company": d.company, "role": d.role, "status": d.status,
            "eligible": sum(in_drive(r) for r in recs),
            "applied": sum(a.source == "student" or any(h.get("stage") == "Applied" for h in a.stage_history or []) for a in apps),
            "shortlisted": sum(_ever_shortlisted(a) for a in apps),
            "offered": sum(o.drive_id == d.id for o in offers),  # every offer made, whatever the decision
            "accepted": sum(o.drive_id == d.id and o.status == "accepted" for o in offers),
        }
        funnel_rows.append(row)
        totals.update({k: row[k] for k in ("eligible", "applied", "shortlisted", "offered", "accepted")})

    n = len(profiles)
    placed = sum(p.placed_status == "placed" for p in profiles)
    return {
        "students": n, "placed": placed, "offered": sum(p.placed_status == "offered" for p in profiles),
        "placed_pct": round(100 * placed / n, 1) if n else 0.0,
        "consent_given": sum(p.has_consent for p in profiles),
        "drives": {"total": len(drives), "open": sum(d.status == "open" for d in drives)},
        "ctc": {"count": len(ctcs), "highest": max(ctcs) if ctcs else None, "median": statistics.median(ctcs) if ctcs else None,
                "average": round(statistics.mean(ctcs), 2) if ctcs else None},
        "by_branch": group("branch"), "by_batch": group("batch_year"), "companies": companies,
        "funnel": {"total": {k: totals[k] for k in ("eligible", "applied", "shortlisted", "offered", "accepted")}, "drives": funnel_rows},
    }


# ---------------- skill-gap heatmap ----------------

def skill_gap(db: Session, inst: str, top_skills: int = 12) -> dict[str, Any]:
    drives = _active_drives(db, inst)
    demand: Counter[str] = Counter()
    names: dict[str, str] = {}
    branch_demand: dict[str, Counter[str]] = defaultdict(Counter)
    branches_all = {p.branch for p in db.scalars(select(StudentProfile).where(StudentProfile.institution_id == inst)) if p.branch}
    from app.campus.drives import rules_of
    from app.models.campus import EligibilityRule

    for d in drives:
        rules = rules_of(db.scalars(select(EligibilityRule).where(EligibilityRule.drive_id == d.id)).first())
        open_to = {b.upper() for b in rules.allowed_branches} or branches_all
        for s in d.skills or []:
            if s.get("type") != "required":
                continue
            demand[s["skill_id"]] += 1
            names[s["skill_id"]] = s["name"]
            for b in open_to:
                branch_demand[b][s["skill_id"]] += 1
    skills = [sid for sid, _ in demand.most_common(top_skills)]
    if not skills:
        return {"skills": [], "branches": [], "cells": [], "recommendations": []}

    space = get_skill_space()
    cal = calibration_for(space.encoder.model_name)
    skill_vecs = space.vectors([{"skill_id": s, "name": names[s]} for s in skills])
    per_branch: dict[str, list[np.ndarray]] = defaultdict(list)  # rows of "has skill" flags
    for user, prof, cand in institution_students(db, inst):
        if not prof.has_consent or cand is None or not prof.branch:
            continue
        have = cand.skills or []
        if not have:
            per_branch[prof.branch].append(np.zeros(len(skills), dtype=bool))
            continue
        sims = cal.skill(skill_vecs @ space.vectors(have).T).max(axis=1)
        per_branch[prof.branch].append(sims >= SKILL_MATCH_THRESHOLD)

    branches = sorted(per_branch)
    cells, recs = [], []
    for b in branches:
        m = np.stack(per_branch[b])
        missing = 1.0 - m.mean(axis=0)
        for j, sid in enumerate(skills):
            pct = round(float(missing[j]) * 100)
            bd = branch_demand.get(b.upper(), Counter())[sid]
            cells.append({"branch": b, "skill_id": sid, "skill": names[sid], "missing_pct": pct, "students": int(m.shape[0]),
                          "drives_demanding": bd})
            if bd > 0 and pct >= 40 and m.shape[0] >= 3:
                recs.append({"branch": b, "skill": names[sid], "missing_pct": pct, "drives": bd, "students": int(m.shape[0]),
                             "text": f"{pct}% of {b} students lack {names[sid]}, required by {bd} drive{'s' if bd != 1 else ''}",
                             "priority": pct * bd})
    recs.sort(key=lambda r: -r["priority"])
    return {"skills": [{"skill_id": s, "name": names[s], "drives": demand[s]} for s in skills], "branches": branches,
            "cells": cells, "recommendations": recs[:10]}


# ---------------- unplaced students ----------------

def unplaced(db: Session, inst: str, per_student: int = 3) -> list[dict[str, Any]]:
    drives = [d for d in _active_drives(db, inst) if d.status == "open"]
    best: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in drives:
        for r in rank_drive(db, d):
            applied = r.application is not None and r.application.stage != "Withdrawn"
            if r.verdict.eligible and r.breakdown is not None and not applied:
                best[r.user.id].append({"drive_id": d.id, "company": d.company, "role": d.role,
                                        "match_percent": round(r.breakdown.score * 100)})
    out = []
    for user, prof, cand in institution_students(db, inst):
        if prof.placed_status != "unplaced" or not prof.has_consent:
            continue
        fits = sorted(best.get(user.id, []), key=lambda x: -x["match_percent"])[:per_student]
        out.append({"user_id": user.id, "roll_no": prof.roll_no, "name": user.full_name, "branch": prof.branch,
                    "cgpa": prof.cgpa, "has_resume": cand is not None, "best_drives": fits})
    out.sort(key=lambda s: (s["best_drives"] == [], s["branch"] or "", s["roll_no"] or ""))
    return out


# ---------------- fairness ----------------

@dataclass
class _Tally:
    eligible: int = 0
    system: int = 0
    actual: int = 0


def fairness(db: Session, inst: str) -> dict[str, Any]:
    """Shortlist rates by gender and branch, for the system's recommendation and the TPO's actual shortlist.

    For each drive with a shortlist of size K, the 'system' set is the top-K eligible students by score.
    Scores never see name or gender, so blind and named views recommend the same students.
    """
    by: dict[str, dict[str, _Tally]] = {"gender": defaultdict(_Tally), "branch": defaultdict(_Tally)}
    drives_used = 0
    for d in _active_drives(db, inst):
        recs: list[StudentRecord] = [r for r in rank_drive(db, d) if in_drive(r)]
        k = sum(1 for r in recs if r.application is not None and _ever_shortlisted(r.application))
        if k == 0:
            continue
        drives_used += 1
        system_ids = {r.user.id for r in [x for x in recs if x.breakdown is not None][:k]}
        for r in recs:
            actual = r.application is not None and _ever_shortlisted(r.application)
            for dim, key in (("gender", r.profile.gender or "not recorded"), ("branch", r.profile.branch or "Unknown")):
                t = by[dim][key]
                t.eligible += 1
                t.system += r.user.id in system_ids
                t.actual += actual

    def table(dim: str) -> dict[str, Any]:
        rows = []
        for k, t in sorted(by[dim].items()):
            shown = t.eligible >= MIN_GROUP
            rows.append({"group": k, "eligible": t.eligible if shown else None, "suppressed": not shown,
                         "system_rate": round(100 * t.system / t.eligible, 1) if shown and t.eligible else None,
                         "actual_rate": round(100 * t.actual / t.eligible, 1) if shown and t.eligible else None})
        def parity(key: str) -> float | None:
            rates = [r[key] for r in rows if r[key] is not None]
            return round(min(rates) / max(rates), 2) if len(rates) >= 2 and max(rates) > 0 else None
        return {"rows": rows, "system_parity": parity("system_rate"), "actual_parity": parity("actual_rate")}

    return {"drives_used": drives_used, "min_group": MIN_GROUP, "gender": table("gender"), "branch": table("branch"),
            "note": ("Rates are shortlisted / eligible across drives. Parity is the lowest group rate divided by the highest "
                     "(below 0.8 deserves a look). Groups under 10 students are hidden. Scores never use name or gender, so "
                     "blind and named reviews start from the same ranking.")}
