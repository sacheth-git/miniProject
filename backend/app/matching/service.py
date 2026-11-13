"""Matching service: candidate profile, FAISS retrieval, filters, re-scoring, explain, gap.

Retrieval: FAISS top-300 by resume embedding (restricted to jobs passing the
filters when any are set), plus the candidate's own imported jobs; then full
re-scoring and sorting.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.jobs import apply_job_filters
from app.core.logging import get_logger
from app.embeddings.documents import job_document
from app.embeddings.encoder import Encoder, get_encoder
from app.embeddings.faiss_index import JobIndex, get_index, responsibilities_text
from app.matching import baselines
from app.matching.calibration import calibration_for
from app.matching.scorer import Breakdown, CandidateProfile, JobFeatures, Scorer, ScorerConfig, SkillSpace, Weights
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.match import Match
from app.skills.taxonomy import get_taxonomy

log = get_logger(__name__)
RETRIEVE_K = 300


class IndexNotReady(RuntimeError):
    pass


@dataclass
class MatchFilters:
    role: str | None = None
    location: str | None = None
    remote: bool | None = None
    job_type: str | None = None
    source: str | None = None
    min_exp: float | None = None
    max_exp: float | None = None
    posted_within: int | None = None

    def active(self) -> bool:
        return any(v is not None for v in vars(self).values())


@dataclass
class RankedJob:
    job: Job
    breakdown: Breakdown
    method_score: float


@dataclass
class MatchRun:
    items: list[RankedJob]
    retrieved: int
    timings_ms: dict[str, float] = field(default_factory=dict)


@lru_cache
def get_skill_space() -> SkillSpace:
    return SkillSpace(get_taxonomy(), get_encoder())


def get_scorer(config: ScorerConfig | None = None, weights: Weights | None = None) -> Scorer:
    enc = get_encoder()
    return Scorer(get_skill_space(), calibration_for(enc.model_name), weights, config)


def candidate_texts(cand: Candidate) -> tuple[str, list[str]]:
    """Full text and section texts used for embeddings (masked sections when bias-aware)."""
    sec = cand.sections or {}
    full = (cand.masked_text if cand.bias_aware else cand.raw_text) or "\n".join(sec.values())
    parts = [sec.get("experience", ""), sec.get("projects", "")]
    sections = [p for p in parts if p.strip()]
    if len(sections) == 2:
        sections.append("\n".join(parts))
    if not sections:  # freshers without experience/projects: summary + skills stand in
        alt = "\n".join(p for p in (sec.get("summary", ""), sec.get("skills", "")) if p.strip())
        if alt:
            sections = [alt]
    return full, sections


def build_profile(cand: Candidate, encoder: Encoder | None = None, space: SkillSpace | None = None) -> CandidateProfile:
    encoder = encoder or get_encoder()
    space = space or get_skill_space()
    full, sections = candidate_texts(cand)
    vecs = encoder.encode([full, *sections])
    return CandidateProfile(
        id=cand.id,
        skills=list(cand.skills or []),
        skill_vecs=space.vectors(list(cand.skills or [])),
        full_vec=vecs[0],
        section_vecs=list(vecs[1:]),
        years=cand.years_experience or 0.0,
        edu_rank=cand.education_rank or 0,
        prefs=dict(cand.preferences or {}),
    )


def job_features(jobs: list[Job], index: JobIndex | None, encoder: Encoder) -> list[JobFeatures]:
    """Vectors from the index when present; encoded on the fly otherwise (imports, new jobs)."""
    missing = [j for j in jobs if index is None or j.id not in index.pos]
    extra: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if missing:
        docs = encoder.encode([job_document(j.title, j.description) for j in missing])
        for j, d in zip(missing, docs):
            r = responsibilities_text(j.title, j.responsibilities or "")
            extra[j.id] = (d, encoder.encode_one(r) if r else d)
    out = []
    for j in jobs:
        if j.id in extra:
            doc, resp = extra[j.id]
        else:
            assert index is not None
            p = index.pos[j.id]
            doc, resp = index.doc[p], index.resp[p]
        out.append(
            JobFeatures(
                id=j.id, title=j.title, required=j.required_skills or [], preferred=j.preferred_skills or [],
                exp_min=j.experience_min, exp_max=j.experience_max, job_type=j.job_type, location=j.location,
                country=j.country, remote=j.remote, description=j.description or "", doc_vec=doc, resp_vec=resp,
            )
        )
    return out


def _method_scores(method: str, cand: Candidate, profile: CandidateProfile, jobs: list[Job],
                   feats: list[JobFeatures], bds: list[Breakdown]) -> np.ndarray:
    if method == "ours":
        return np.array([b.score for b in bds], dtype=np.float32)
    if method == "sbert_section":
        return np.array([b.sem for b in bds], dtype=np.float32)
    if method == "sbert_whole":
        return baselines.sbert_whole(profile.full_vec, np.stack([f.doc_vec for f in feats]))
    full, _ = candidate_texts(cand)
    texts = [job_document(j.title, j.description) for j in jobs]
    if method == "tfidf":
        return baselines.tfidf_scores(full, texts)
    if method == "bm25":
        return baselines.bm25_scores(full, texts)
    if method == "keyword_jaccard":
        rs = {s["skill_id"] for s in cand.skills or []}
        return baselines.keyword_jaccard(rs, [{s["skill_id"] for s in (j.required_skills or []) + (j.preferred_skills or [])} for j in jobs])
    raise ValueError(f"Unknown method {method}")


def match(
    db: Session,
    cand: Candidate,
    filters: MatchFilters | None = None,
    limit: int = 20,
    method: str = "ours",
    k: int = RETRIEVE_K,
    persist: bool = True,
    scorer: Scorer | None = None,
) -> MatchRun:
    if method not in baselines.METHODS:
        raise ValueError(f"Unknown method {method}; choose from {baselines.METHODS}")
    t = time.perf_counter()
    timings: dict[str, float] = {}

    def lap(name: str) -> None:
        nonlocal t
        now = time.perf_counter()
        timings[name] = round((now - t) * 1000, 1)
        t = now

    index = get_index()
    if index is None or len(index) == 0:
        raise IndexNotReady("Job index not built. Run: .\\.venv\\Scripts\\python.exe scripts\\build_index.py")
    encoder = get_encoder()
    scorer = scorer or get_scorer()
    filters = filters or MatchFilters()
    profile = build_profile(cand, encoder)
    lap("profile")

    allowed: list[int] | None = None
    if filters.active():
        ids = db.scalars(apply_job_filters(select(Job.id), **_filter_kwargs(filters), owner_id=None)).all()
        allowed = [index.pos[i] for i in ids if i in index.pos]
    hits = index.search(profile.full_vec, k, allowed)
    own_ids = db.scalars(apply_job_filters(select(Job.id).where(Job.owner_id == cand.id), **_filter_kwargs(filters), owner_id=cand.id)).all()
    cand_ids = list(dict.fromkeys([h[0] for h in hits] + list(own_ids)))
    lap("retrieve")

    jobs_by_id = {j.id: j for j in db.scalars(select(Job).where(Job.id.in_(cand_ids))).all()}
    jobs = [jobs_by_id[i] for i in cand_ids if i in jobs_by_id]
    feats = job_features(jobs, index, encoder)
    lap("load")

    bds = [scorer.score(profile, f, index.idf) for f in feats]
    ms = _method_scores(method, cand, profile, jobs, feats, bds) if jobs else np.zeros(0)
    order = np.argsort(-ms, kind="stable")[:limit]
    items = [RankedJob(jobs[i], bds[i], float(ms[i])) for i in order]
    lap("score")

    if persist and method == "ours":
        _persist(db, cand.id, items)
        lap("persist")
    log.info("match %s: %d retrieved, %d returned, %s", cand.id, len(jobs), len(items), timings)
    return MatchRun(items=items, retrieved=len(jobs), timings_ms=timings)


def _filter_kwargs(f: MatchFilters) -> dict[str, Any]:
    return {
        "role": f.role, "location": f.location, "remote": f.remote, "job_type": f.job_type, "source": f.source,
        "min_exp": f.min_exp, "max_exp": f.max_exp, "posted_within": f.posted_within,
    }


def _sm_dicts(items: list[Any]) -> list[dict[str, Any]]:
    return [vars(m) for m in items]


def _persist(db: Session, candidate_id: str, items: list[RankedJob]) -> None:
    db.execute(delete(Match).where(Match.candidate_id == candidate_id))
    for rank, it in enumerate(items, 1):
        b = it.breakdown
        db.add(
            Match(
                candidate_id=candidate_id, job_id=it.job.id, rank=rank, score=b.score, sem_score=b.sem,
                skill_score=b.skill, context_score=b.context, penalty=b.penalty,
                matched_skills=_sm_dicts(b.matched), missing_required=_sm_dicts(b.missing_required),
                missing_preferred=_sm_dicts(b.missing_preferred),
                evidence={"context_parts": b.context_parts, "sem_section": b.sem_section, "sem_full": b.sem_full},
            )
        )
    db.commit()
