"""Drive skills, eligibility over an institution's students, and ranked shortlists.

Ranking reuses the open-market scorer: the drive becomes JobFeatures (its JD embedded
like any job) and each eligible student's latest resume becomes a CandidateProfile.
Skill weights default to type x corpus IDF and can be overridden by the TPO.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.eligibility.engine import DriveFacts, Rules, StudentFacts, Verdict, evaluate
from app.embeddings.documents import job_document
from app.embeddings.encoder import get_encoder
from app.embeddings.faiss_index import get_index, responsibilities_text
from app.ingestion.normalizer import split_responsibilities
from app.matching.scorer import Breakdown, JobFeatures
from app.matching.service import build_profile, get_scorer
from app.models.campus import Drive, DriveApplication, EligibilityRule
from app.models.candidate import Candidate
from app.models.user import Institution, StudentProfile, User
from app.placement_policy.policy import Policy
from app.skills.extractor import get_extractor
from app.skills.jd_skill_weighter import PREFERRED_TYPE, REQUIRED_TYPE, extract_jd_skills

DRIVE_EXPERIENCE = {"internship": (0.0, 1.0), "fte": (0.0, 2.0), "intern+ppo": (0.0, 1.0)}


def extract_drive_skills(jd_text: str) -> list[dict[str, Any]]:
    """Auto-extracted skills with default weights (type x IDF over the job corpus)."""
    req, pref = extract_jd_skills(jd_text, get_extractor())
    index = get_index()
    idf = index.idf if index else {}
    out: list[dict[str, Any]] = []
    for s, t in [(s, REQUIRED_TYPE) for s in req] + [(s, PREFERRED_TYPE) for s in pref]:
        out.append({
            "skill_id": s.skill_id, "name": s.name, "type": s.type,
            "weight": round(t * idf.get(s.skill_id, 1.0), 3), "evidence": s.evidence,
        })
    return out


def drive_features(drive: Drive) -> JobFeatures:
    enc = get_encoder()
    doc = enc.encode_one(job_document(f"{drive.role} at {drive.company}", drive.jd_text))
    resp_text = responsibilities_text(drive.role, split_responsibilities(drive.jd_text))
    resp = enc.encode_one(resp_text) if resp_text else doc
    lo, hi = DRIVE_EXPERIENCE.get(drive.job_type, (0.0, 2.0))
    skills = drive.skills or []
    return JobFeatures(
        id=drive.id, title=drive.role,
        required=[s for s in skills if s.get("type") == "required"],
        preferred=[s for s in skills if s.get("type") != "required"],
        exp_min=lo, exp_max=hi,
        job_type="internship" if drive.job_type in ("internship", "intern+ppo") else "full-time",
        location=drive.location, country="India", remote=False, description=drive.jd_text,
        doc_vec=doc, resp_vec=resp,
    )


def rules_of(r: EligibilityRule | None) -> Rules:
    if r is None:
        return Rules()
    return Rules(
        allowed_branches=list(r.allowed_branches or []), batch_years=list(r.batch_years or []), min_cgpa=r.min_cgpa,
        max_active_backlogs=r.max_active_backlogs, max_history_backlogs=r.max_history_backlogs,
        min_tenth=r.min_tenth, min_twelfth=r.min_twelfth, custom_rules=list(r.custom_rules or []),
    )


@dataclass
class StudentRecord:
    user: User
    profile: StudentProfile
    candidate: Candidate | None
    verdict: Verdict
    application: DriveApplication | None = None
    breakdown: Breakdown | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def institution_students(db: Session, institution_id: str) -> list[tuple[User, StudentProfile, Candidate | None]]:
    rows = db.execute(
        select(User, StudentProfile)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(StudentProfile.institution_id == institution_id, User.is_active.is_(True))
    ).all()
    uids = [u.id for u, _ in rows]
    latest: dict[str, Candidate] = {}
    if uids:
        for c in db.scalars(select(Candidate).where(Candidate.user_id.in_(uids)).order_by(Candidate.created_at)):
            latest[c.user_id] = c  # type: ignore[index]  # last one wins: newest
    return [(u, p, latest.get(u.id)) for u, p in rows]


def facts(p: StudentProfile, has_resume: bool) -> StudentFacts:
    return StudentFacts(
        branch=p.branch, batch_year=p.batch_year, cgpa=p.cgpa, active_backlogs=p.active_backlogs or 0,
        history_backlogs=p.history_backlogs or 0, tenth_pct=p.tenth_pct, twelfth_pct=p.twelfth_pct,
        diploma_pct=p.diploma_pct, placed_status=p.placed_status or "unplaced",
        current_offer_ctc=p.current_best_offer_ctc, consent=p.has_consent,
        consent_pending=p.consent_given_at is None and p.consent_withdrawn_at is None, has_resume=has_resume,
    )


def evaluate_drive(db: Session, drive: Drive) -> list[StudentRecord]:
    inst = db.get(Institution, drive.institution_id)
    policy = Policy.from_settings(inst.settings if inst else None)
    rules = rules_of(db.scalars(select(EligibilityRule).where(EligibilityRule.drive_id == drive.id)).first())
    dfacts = DriveFacts(category=drive.category, ctc_lpa=drive.ctc_lpa)
    apps = {a.student_id: a for a in db.scalars(select(DriveApplication).where(DriveApplication.drive_id == drive.id))}
    out = []
    for user, prof, cand in institution_students(db, drive.institution_id):
        v = evaluate(facts(prof, cand is not None), rules, dfacts, policy)
        out.append(StudentRecord(user, prof, cand, v, apps.get(user.id)))
    return out


def rank_drive(db: Session, drive: Drive, records: list[StudentRecord] | None = None) -> list[StudentRecord]:
    """Score every eligible student with a resume; eligible first by score, then the rest."""
    records = records if records is not None else evaluate_drive(db, drive)
    feats = drive_features(drive)
    scorer = get_scorer()
    index = get_index()
    idf = index.idf if index else {}
    for r in records:
        if r.verdict.eligible and r.candidate is not None:
            r.breakdown = scorer.score(build_profile(r.candidate), feats, idf)
    records.sort(key=lambda r: (not r.verdict.eligible, r.breakdown is None, -(r.breakdown.score if r.breakdown else 0), r.profile.roll_no or ""))
    return records
