"""Placement readiness: average match vs open drives + profile completeness + ATS-friendliness.

readiness = 0.5 * match + 0.25 * completeness + 0.25 * ats   (each in [0, 1])
Also returns the top 3 actions that would raise it most.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.campus.drives import StudentRecord, evaluate_drive, rank_drive
from app.models.campus import Drive
from app.models.candidate import Candidate
from app.models.user import StudentProfile, User
from app.privacy.pii_mask import EMAIL_RE, PHONE_RE


def has_phone(text: str) -> bool:
    return any(10 <= sum(ch.isdigit() for ch in m.group(0)) <= 13 for m in PHONE_RE.finditer(text))

W_MATCH, W_COMPLETE, W_ATS = 0.5, 0.25, 0.25
ACTION_VERBS = re.compile(
    r"\b(built|developed|designed|implemented|led|created|improved|reduced|increased|automated|deployed|optimi[sz]ed|"
    r"analy[sz]ed|launched|managed|wrote|trained|integrated|migrated|delivered)\b",
    re.I,
)
METRIC = re.compile(r"\b\d+(\.\d+)?\s?(%|x|ms|k|users|students|customers|hours|lpa)\b|\b\d{2,}\b", re.I)


@dataclass
class Readiness:
    score: float
    match: float | None
    completeness: float
    ats: float
    drives_considered: int
    checks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)


def _completeness(cand: Candidate | None, prof: StudentProfile | None) -> tuple[float, list[dict[str, Any]]]:
    sec = (cand.sections if cand else {}) or {}
    checks = [
        ("Resume uploaded", cand is not None, "Upload your resume"),
        ("At least 8 skills listed", bool(cand) and len(cand.skills or []) >= 8, "List more of your technical skills in a Skills section"),
        ("Skills section", "skills" in sec, "Add a clear 'Skills' section"),
        ("Projects or experience", "projects" in sec or "experience" in sec, "Add projects or internships with what you built"),
        ("Education", "education" in sec, "Add an 'Education' section with your degree"),
        ("Summary", "summary" in sec, "Add a two-line summary at the top"),
        ("Certifications", "certifications" in sec, "Add relevant certifications or courses"),
        ("Academic record complete", bool(prof and prof.cgpa is not None and prof.tenth_pct is not None
                                          and (prof.twelfth_pct is not None or prof.diploma_pct is not None)),
         "Ask your placement office to complete your CGPA and 10th / 12th marks"),
        ("Job preferences set", bool(cand and (cand.preferences or {}).get("job_types")), "Set your preferred job types and locations"),
    ]
    out = [{"label": label, "ok": bool(ok), "fix": fix} for label, ok, fix in checks]
    return sum(c["ok"] for c in out) / len(out), out


def _ats(cand: Candidate | None) -> tuple[float, list[dict[str, Any]]]:
    if cand is None:
        return 0.0, [{"label": "Resume uploaded", "ok": False, "fix": "Upload your resume"}]
    text = cand.raw_text or cand.masked_text or ""
    words = len(text.split())
    bullets = len(re.findall(r"^\s*-\s", text, re.M))
    body = "\n".join((cand.sections or {}).get(k, "") for k in ("experience", "projects"))
    checks = [
        ("Readable length (250-900 words)", 250 <= words <= 900, "Aim for one page of 250-900 words" if words < 250 else "Trim to one or two pages"),
        ("Fits on 1-2 pages", (cand.pages or 1) <= 2, "Keep the resume to two pages at most"),
        ("Standard section headings", len([k for k in (cand.sections or {}) if k != "header"]) >= 4, "Use standard headings: Summary, Skills, Experience, Projects, Education"),
        ("Contact details", bool(EMAIL_RE.search(text)) and has_phone(text), "Put your email and phone number at the top"),
        ("Bullet points", bullets >= 4, "Describe projects and internships as bullet points"),
        ("Action verbs", len(ACTION_VERBS.findall(body)) >= 3, "Start bullets with verbs like built, designed, improved"),
        ("Quantified results", len(METRIC.findall(body)) >= 2, "Add numbers: accuracy, users, time saved, % improvement"),
    ]
    out = [{"label": label, "ok": bool(ok), "fix": fix} for label, ok, fix in checks]
    return sum(c["ok"] for c in out) / len(out), out


def compute(db: Session, student: User, top_drives: int = 5) -> Readiness:
    prof = db.scalars(select(StudentProfile).where(StudentProfile.user_id == student.id)).first()
    cand = db.scalars(select(Candidate).where(Candidate.user_id == student.id).order_by(Candidate.created_at.desc())).first()
    completeness, c_checks = _completeness(cand, prof)
    ats, a_checks = _ats(cand)

    match: float | None = None
    missing: Counter[str] = Counter()
    considered = 0
    if prof is not None and cand is not None:
        scores: list[float] = []
        drives = db.scalars(select(Drive).where(Drive.institution_id == prof.institution_id, Drive.status == "open")).all()
        for d in drives:
            rec: StudentRecord | None = next((r for r in evaluate_drive(db, d) if r.user.id == student.id), None)
            if rec is None or not rec.verdict.eligible:
                continue
            rank_drive(db, d, [rec])
            if rec.breakdown is not None:
                scores.append(rec.breakdown.score)
                missing.update(m.name for m in rec.breakdown.missing_required)
        considered = len(scores)
        if scores:
            match = sum(sorted(scores, reverse=True)[:top_drives]) / min(len(scores), top_drives)

    parts = [(W_COMPLETE, completeness), (W_ATS, ats)] + ([(W_MATCH, match)] if match is not None else [])
    score = sum(w * v for w, v in parts) / sum(w for w, _ in parts)

    actions: list[dict[str, Any]] = []
    for skill, n in missing.most_common(2):
        actions.append({"kind": "skill", "text": f"Learn {skill}: required by {n} open drive{'s' if n > 1 else ''} you're eligible for",
                        "gain": W_MATCH * 0.1 * n})
    for c in c_checks:
        if not c["ok"]:
            actions.append({"kind": "profile", "text": c["fix"], "gain": W_COMPLETE / len(c_checks)})
    for c in a_checks:
        if not c["ok"]:
            actions.append({"kind": "resume", "text": c["fix"], "gain": W_ATS / len(a_checks)})
    actions.sort(key=lambda a: -a["gain"])
    seen: set[str] = set()
    top = [a for a in actions if not (a["text"] in seen or seen.add(a["text"]))][:3]  # type: ignore[func-returns-value]
    return Readiness(
        score=round(score, 3), match=round(match, 3) if match is not None else None, completeness=round(completeness, 3),
        ats=round(ats, 3), drives_considered=considered, checks={"profile": c_checks, "resume": a_checks},
        actions=[{"kind": a["kind"], "text": a["text"]} for a in top],
    )
