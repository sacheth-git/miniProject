"""Job API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ApplyOptionOut(BaseModel):
    publisher: str
    url: str
    is_direct: bool = False


class JDSkillOut(BaseModel):
    skill_id: str
    name: str
    type: str
    evidence: str = ""


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    title: str
    company: str
    location: str | None
    country: str | None
    remote: bool
    job_type: str
    experience_min: float | None
    experience_max: float | None
    posted_at: datetime | None
    apply_url: str
    apply_options: list[ApplyOptionOut]
    required_skills: list[JDSkillOut]
    preferred_skills: list[JDSkillOut]
    is_active: bool
    dedup_group_id: str | None


class JobDetail(JobSummary):
    description: str
    responsibilities: str
    source_url: str | None
    first_seen_at: datetime
    last_checked_at: datetime | None


class JobPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobSummary]


class SourceStatus(BaseModel):
    source: str
    configured: bool
    reason: str = ""
    active_jobs: int
    total_jobs: int
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_fetched: int = 0
    last_created: int = 0
    last_updated: int = 0
    last_deactivated: int = 0
    last_errors: int = 0
    last_message: str = ""


class SourcesStatusOut(BaseModel):
    running: bool
    total_active: int
    total_active_unique: int
    sources: list[SourceStatus]


class IngestRequest(BaseModel):
    sources: list[str] | None = Field(default=None, description="Subset of sources; all if omitted")
    wait: bool = Field(default=False, description="Run synchronously and return the report")


class ImportTextIn(BaseModel):
    text: str = Field(min_length=30, max_length=50_000, description="Job description text")
    url: HttpUrl | None = None
    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    candidate_id: str | None = Field(default=None, description="Owner; imported jobs are private to them")


class ImportResult(BaseModel):
    created: int
    updated: int
    jobs: list[JobSummary]
    skipped_files: list[str] = Field(default_factory=list)
