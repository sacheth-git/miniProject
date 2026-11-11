"""Resume / candidate API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SkillOut(BaseModel):
    skill_id: str
    name: str
    esco_uri: str | None = None
    confidence: float
    evidence: str = ""
    section: str = ""
    method: str = "phrase"
    mentions: int = 1


class ProcessingStep(BaseModel):
    name: str
    ms: float
    detail: str = ""


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str | None
    sections: dict[str, str]
    skills: list[SkillOut]
    years_experience: float
    education_level: str
    bias_aware: bool
    preferences: dict[str, Any] = Field(default_factory=dict)
    pages: int
    masked_text: str | None = None
    created_at: datetime


class UploadResponse(CandidateOut):
    steps: list[ProcessingStep] = Field(default_factory=list)


class SkillEdit(BaseModel):
    add: list[str] = Field(default_factory=list, description="Skill names to add")
    remove: list[str] = Field(default_factory=list, description="skill_ids to remove")


class PreferencesIn(BaseModel):
    target_role: str | None = None
    locations: list[str] = Field(default_factory=list)
    remote_ok: bool = True
    job_types: list[str] = Field(default_factory=list)  # internship / full-time / contract
