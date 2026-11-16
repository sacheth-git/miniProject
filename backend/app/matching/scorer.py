"""Skill-weighted, section-level matching score.

S = alpha*Sem + beta*Skill + gamma*Context - delta*Penalty   (clipped to [0, 1])

Sem     = clip(0.7 * max_s cal(cos(resume_section_s, JD responsibilities))
               + 0.3 * cal(cos(full resume, full JD)))
Skill   = (sum_j w_j * best_j + K * P0) / (sum_j w_j + K), best_j = max_i cal(cos(r_i, s_j)), 0 if < 0.5
          (shrinkage toward P0 = 0.5 with K = 2: a JD listing one skill cannot give 100%,
           and a JD with no extracted skills is neutral)
          w_j = type_j * idf_j  (type: 1.0 required, 0.5 preferred; idf in [0.5, 1.5])
Context = mean(experience fit, job-type fit, location fit, education fit)
Penalty = fraction of required skills with best_j < 0.5

ScorerConfig switches each ingredient off for the ablation study.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from app.core.config import BACKEND_DIR, get_settings
from app.embeddings.encoder import Encoder
from app.matching.calibration import Calibration
from app.parsing.profile import EDUCATION_LEVELS
from app.skills.jd_skill_weighter import PREFERRED_TYPE, REQUIRED_TYPE
from app.skills.taxonomy import Taxonomy

SKILL_MATCH_THRESHOLD = 0.5
SECTION_WEIGHT, FULL_WEIGHT = 0.7, 0.3
SHRINK_K, SHRINK_PRIOR = 2.0, 0.5
DEGREE_LINE = re.compile(r"\b(degree|bachelor|master|ph\.?\s?d|graduate|qualification|b\.?\s?tech|m\.?\s?tech|b\.?e\.?|education)\b", re.I)


@dataclass(frozen=True)
class Weights:
    alpha: float
    beta: float
    gamma: float
    delta: float

    @classmethod
    def from_settings(cls) -> Weights:
        """Weights from data/learned_weights.json when they were learned from HUMAN labels
        (eval/evaluate.py writes it); otherwise the configured defaults (W_ALPHA... in .env).
        Weights learned from proxy labels are reported in the evaluation but never applied."""
        learned = BACKEND_DIR / "data" / "learned_weights.json"
        if learned.exists():
            try:
                w = json.loads(learned.read_text(encoding="utf-8"))
                if w.get("label_source") == "human" and w.get("val_ndcg10", 0) >= w.get("default_val_ndcg10", 1):
                    return cls(float(w["alpha"]), float(w["beta"]), float(w["gamma"]), float(w["delta"]))
            except (ValueError, KeyError, OSError):
                pass  # malformed file: fall back to the configured defaults
        s = get_settings()
        return cls(s.w_alpha, s.w_beta, s.w_gamma, s.w_delta)


@dataclass(frozen=True)
class ScorerConfig:
    use_sections: bool = True  # False: Sem = full-document similarity only
    use_skill: bool = True
    use_idf: bool = True
    use_type_weights: bool = True  # required 1.0 / preferred 0.5
    soft_skill_match: bool = True  # False: exact skill-id match only
    use_context: bool = True
    use_penalty: bool = True
    calibrate: bool = True
    skill_shrinkage: bool = True


@dataclass
class CandidateProfile:
    id: str
    skills: list[dict[str, Any]]
    skill_vecs: np.ndarray  # (k, d)
    full_vec: np.ndarray
    section_vecs: list[np.ndarray]
    years: float
    edu_rank: int
    prefs: dict[str, Any]


@dataclass
class JobFeatures:
    id: str
    title: str
    required: list[dict[str, Any]]
    preferred: list[dict[str, Any]]
    exp_min: float | None
    exp_max: float | None
    job_type: str
    location: str | None
    country: str | None
    remote: bool
    description: str
    doc_vec: np.ndarray
    resp_vec: np.ndarray


@dataclass
class SkillMatch:
    skill_id: str
    name: str
    type: str
    weight: float
    similarity: float
    resume_skill: str | None
    resume_evidence: str
    jd_evidence: str


@dataclass
class Breakdown:
    job_id: str
    score: float
    sem: float
    sem_section: float
    sem_full: float
    skill: float
    context: float
    context_parts: dict[str, float]
    penalty: float
    matched: list[SkillMatch] = field(default_factory=list)
    missing_required: list[SkillMatch] = field(default_factory=list)
    missing_preferred: list[SkillMatch] = field(default_factory=list)
    raw: float = 0.0
    # internals reused by the gap advisor
    _jd_skills: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _jd_vecs: np.ndarray | None = field(default=None, repr=False)
    _best: np.ndarray | None = field(default=None, repr=False)
    _weights: np.ndarray | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        return d


class SkillSpace:
    """Skill name -> vector, using taxonomy-name embeddings (cached) and on-the-fly custom names."""

    def __init__(self, taxonomy: Taxonomy, encoder: Encoder) -> None:
        self.tax = taxonomy
        self.encoder = encoder
        self._row = {s.id: i for i, s in enumerate(taxonomy.skills)}
        self._mat: np.ndarray | None = None

    def _matrix(self) -> np.ndarray:
        if self._mat is None:
            self._mat = self.encoder.encode([s.name for s in self.tax.skills])
        return self._mat

    def vectors(self, skills: list[dict[str, Any]]) -> np.ndarray:
        if not skills:
            return np.zeros((0, self.encoder.dim), dtype=np.float32)
        mat = self._matrix()
        out = np.zeros((len(skills), mat.shape[1]), dtype=np.float32)
        custom: list[tuple[int, str]] = []
        for i, s in enumerate(skills):
            row = self._row.get(s["skill_id"])
            if row is None:
                custom.append((i, s["name"]))
            else:
                out[i] = mat[row]
        if custom:
            for (i, _), v in zip(custom, self.encoder.encode([n for _, n in custom])):
                out[i] = v
        return out


def required_education_rank(description: str) -> int | None:
    ranks: list[int] = []
    for line in description.splitlines():
        if not DEGREE_LINE.search(line):
            continue
        for _label, rank, pat in EDUCATION_LEVELS:
            if rank >= 3 and pat.search(line):  # only degree-level requirements matter
                ranks.append(rank)
    return min(ranks) if ranks else None


def experience_fit(years: float, lo: float | None, hi: float | None) -> float:
    if lo is not None and years < lo:
        return max(0.0, 1.0 - (lo - years) / 3.0)
    if hi is not None and years > hi:
        return max(0.0, 1.0 - (years - hi) / 5.0)  # over-qualification decays slower
    return 1.0


def job_type_fit(job_type: str, prefs: dict[str, Any], years: float) -> float:
    wanted = prefs.get("job_types") or []
    if wanted:
        return 1.0 if job_type in wanted else 0.2
    if job_type == "internship" and years >= 2:
        return 0.4
    return 1.0


def location_fit(location: str | None, country: str | None, remote: bool, prefs: dict[str, Any]) -> float:
    wanted = [w.lower() for w in prefs.get("locations") or [] if w.strip()]
    if not wanted:
        return 1.0
    hay = f"{location or ''} {country or ''}".lower()
    if any(w in hay for w in wanted):
        return 1.0
    if remote and prefs.get("remote_ok", True):
        return 1.0
    return 0.2


def education_fit(cand_rank: int, description: str) -> float:
    req = required_education_rank(description)
    if req is None or cand_rank == 0 or cand_rank >= req:
        return 1.0
    return max(0.0, 1.0 - 0.4 * (req - cand_rank))


class Scorer:
    def __init__(
        self,
        space: SkillSpace,
        calibration: Calibration,
        weights: Weights | None = None,
        config: ScorerConfig | None = None,
    ) -> None:
        self.space = space
        self.cal = calibration
        self.w = weights or Weights.from_settings()
        self.cfg = config or ScorerConfig()

    # ---- similarity helpers ----
    def _doc(self, c: float) -> float:
        return float(self.cal.doc(c)) if self.cfg.calibrate else max(0.0, float(c))

    def _skill_sims(self, jd_vecs: np.ndarray, cand: CandidateProfile, jd_ids: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """(best similarity per JD skill, argmax resume-skill index)."""
        m = len(jd_ids)
        if m == 0 or not cand.skills:
            return np.zeros(m, np.float32), np.full(m, -1)
        if not self.cfg.soft_skill_match:
            have = {s["skill_id"]: i for i, s in enumerate(cand.skills)}
            idx = np.array([have.get(j, -1) for j in jd_ids])
            return (idx >= 0).astype(np.float32), idx
        raw = jd_vecs @ cand.skill_vecs.T
        sims = self.cal.skill(raw) if self.cfg.calibrate else np.clip(raw, 0, 1)
        arg = sims.argmax(axis=1)
        best = sims[np.arange(m), arg]
        best = np.where(best >= SKILL_MATCH_THRESHOLD, best, 0.0).astype(np.float32)
        return best, arg

    def jd_weights(self, req: list[dict[str, Any]], pref: list[dict[str, Any]], idf: dict[str, float]) -> np.ndarray:
        out = []
        for s, t in [(s, REQUIRED_TYPE) for s in req] + [(s, PREFERRED_TYPE) for s in pref]:
            if s.get("weight") is not None:  # set explicitly (campus drives: TPO-edited)
                out.append(float(s["weight"]))
                continue
            tw = t if self.cfg.use_type_weights else 1.0
            iw = idf.get(s["skill_id"], 1.0) if self.cfg.use_idf else 1.0
            out.append(tw * iw)
        return np.asarray(out, dtype=np.float32)

    # ---- main ----
    def score(self, cand: CandidateProfile, job: JobFeatures, idf: dict[str, float]) -> Breakdown:
        sem_full = self._doc(float(cand.full_vec @ job.doc_vec))
        if self.cfg.use_sections and cand.section_vecs:
            sem_section = max(self._doc(float(v @ job.resp_vec)) for v in cand.section_vecs)
            sem = float(np.clip(SECTION_WEIGHT * sem_section + FULL_WEIGHT * sem_full, 0, 1))
        else:
            sem_section, sem = sem_full, sem_full

        jd_skills = job.required + job.preferred
        n_req = len(job.required)
        jd_ids = [s["skill_id"] for s in jd_skills]
        jd_vecs = self.space.vectors(jd_skills) if jd_skills else np.zeros((0, cand.full_vec.shape[0]), np.float32)
        best, arg = self._skill_sims(jd_vecs, cand, jd_ids)
        weights = self.jd_weights(job.required, job.preferred, idf)

        skill = self._skill_value(weights, best)
        penalty = float((best[:n_req] < SKILL_MATCH_THRESHOLD).mean()) if n_req else 0.0

        parts = {
            "experience": experience_fit(cand.years, job.exp_min, job.exp_max),
            "job_type": job_type_fit(job.job_type, cand.prefs, cand.years),
            "location": location_fit(job.location, job.country, job.remote, cand.prefs),
            "education": education_fit(cand.edu_rank, job.description),
        }
        context = float(np.mean(list(parts.values())))

        bd = Breakdown(
            job_id=job.id, score=0.0, sem=sem, sem_section=sem_section, sem_full=sem_full,
            skill=skill, context=context, context_parts=parts, penalty=penalty,
            _jd_skills=jd_skills, _jd_vecs=jd_vecs, _best=best, _weights=weights,
        )
        self._finish(bd)
        self._attach_skills(bd, cand, best, arg, weights, n_req)
        return bd

    def _skill_value(self, weights: np.ndarray, best: np.ndarray) -> float:
        num, den = float((weights * best).sum()), float(weights.sum())
        if self.cfg.skill_shrinkage:
            return (num + SHRINK_K * SHRINK_PRIOR) / (den + SHRINK_K)
        return num / den if den > 0 else SHRINK_PRIOR

    def combine(self, sem: float, skill: float, context: float, penalty: float) -> tuple[float, float]:
        w, c = self.w, self.cfg
        beta = w.beta if c.use_skill else 0.0
        gamma = w.gamma if c.use_context else 0.0
        delta = w.delta if c.use_penalty else 0.0
        raw = w.alpha * sem + beta * skill + gamma * context - delta * penalty
        norm = w.alpha + beta + gamma
        return float(np.clip(raw / norm if norm > 0 else 0.0, 0.0, 1.0)), raw

    def _finish(self, bd: Breakdown) -> None:
        bd.score, bd.raw = self.combine(bd.sem, bd.skill, bd.context, bd.penalty)

    @staticmethod
    def _attach_skills(
        bd: Breakdown, cand: CandidateProfile, best: np.ndarray, arg: np.ndarray, weights: np.ndarray, n_req: int
    ) -> None:
        for j, s in enumerate(bd._jd_skills):
            matched = best[j] >= SKILL_MATCH_THRESHOLD
            r = cand.skills[int(arg[j])] if matched and int(arg[j]) >= 0 else None
            sm = SkillMatch(
                skill_id=s["skill_id"], name=s["name"], type="required" if j < n_req else "preferred",
                weight=round(float(weights[j]), 3), similarity=round(float(best[j]), 3),
                resume_skill=r["name"] if r else None, resume_evidence=(r or {}).get("evidence", ""),
                jd_evidence=s.get("evidence", ""),
            )
            if matched:
                bd.matched.append(sm)
            elif j < n_req:
                bd.missing_required.append(sm)
            else:
                bd.missing_preferred.append(sm)
        bd.matched.sort(key=lambda m: (-m.weight * m.similarity, m.name))

    def with_extra_skill(self, bd: Breakdown, extra_vec: np.ndarray, extra_id: str) -> float:
        """Score after adding one skill to the resume (Sem and Context unchanged)."""
        if not bd._jd_skills or bd._best is None or bd._weights is None or bd._jd_vecs is None:
            return bd.score  # nothing in the JD for a new skill to match
        if self.cfg.soft_skill_match:
            raw = bd._jd_vecs @ extra_vec
            add = self.cal.skill(raw) if self.cfg.calibrate else np.clip(raw, 0, 1)
            add = np.where(add >= SKILL_MATCH_THRESHOLD, add, 0.0)
        else:
            add = np.array([1.0 if s["skill_id"] == extra_id else 0.0 for s in bd._jd_skills], np.float32)
        best = np.maximum(bd._best, add)
        skill = self._skill_value(bd._weights, best)
        n_req = sum(1 for m in bd.matched + bd.missing_required + bd.missing_preferred if m.type == "required")
        penalty = float((best[:n_req] < SKILL_MATCH_THRESHOLD).mean()) if n_req else 0.0
        return self.combine(bd.sem, skill, bd.context, penalty)[0]
