"""Match / explain / gap response schemas."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.job import JobSummary


class SkillMatchOut(BaseModel):
    skill_id: str
    name: str
    type: str
    weight: float
    similarity: float
    resume_skill: str | None = None
    resume_evidence: str = ""
    jd_evidence: str = ""


class BreakdownOut(BaseModel):
    score: float
    sem: float
    sem_section: float
    sem_full: float
    skill: float
    context: float
    context_parts: dict[str, float]
    penalty: float


class MatchItem(BaseModel):
    rank: int
    match_percent: int
    method_score: float
    job: JobSummary
    breakdown: BreakdownOut
    matched_skills: list[SkillMatchOut]
    missing_required: list[SkillMatchOut]
    missing_preferred: list[SkillMatchOut]


class MatchResponse(BaseModel):
    candidate_id: str
    method: str
    retrieved: int
    returned: int
    timings_ms: dict[str, float]
    items: list[MatchItem]


class ExplainResponse(BreakdownOut):
    job_id: str
    matched: list[SkillMatchOut]
    missing_required: list[SkillMatchOut]
    missing_preferred: list[SkillMatchOut]
    weights: dict[str, float]
    contributions: dict[str, float]
    summary: str


class GapExampleJob(BaseModel):
    id: str
    title: str
    company: str


class GapSkill(BaseModel):
    skill_id: str
    name: str
    jobs_improved: int
    avg_gain: float
    total_gain: float
    message: str
    example_jobs: list[GapExampleJob]


class GapResponse(BaseModel):
    jobs_considered: int
    by_total_gain: list[GapSkill]
    by_jobs_improved: list[GapSkill]
