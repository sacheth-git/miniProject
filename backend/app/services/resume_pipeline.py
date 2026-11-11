"""End-to-end resume processing: PDF -> sections -> masking -> skills -> profile."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.parsing.pdf_parser import extract_text
from app.parsing.profile import education_level, years_of_experience
from app.parsing.section_detector import detect_sections
from app.privacy.pii_mask import guess_name, mask_pii
from app.skills.extractor import SkillExtractor, get_extractor

log = get_logger(__name__)


@dataclass
class ResumeResult:
    raw_text: str
    masked_text: str | None
    sections: dict[str, str]
    skills: list[dict[str, Any]]
    years_experience: float
    education_level: str
    education_rank: int
    pages: int
    steps: list[dict[str, Any]] = field(default_factory=list)


class _Timer:
    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self._t = time.perf_counter()

    def lap(self, name: str, detail: str = "") -> None:
        now = time.perf_counter()
        self.steps.append({"name": name, "ms": round((now - self._t) * 1000, 1), "detail": detail})
        self._t = now


def process_text(
    text: str,
    bias_aware: bool = True,
    extractor: SkillExtractor | None = None,
    use_embeddings: bool = True,
    pages: int = 1,
    timer: _Timer | None = None,
) -> ResumeResult:
    timer = timer or _Timer()
    extractor = extractor or get_extractor()

    sections = detect_sections(text)
    timer.lap("detect_sections", ", ".join(k for k in sections if k != "header"))

    masked_text: str | None = None
    work_sections = sections
    if bias_aware:
        name = guess_name(text)
        masked_text = mask_pii(text, name).text
        work_sections = {k: mask_pii(v, name).text for k, v in sections.items()}
        timer.lap("mask_pii", "name, contact, gender words, institutions")

    skills = extractor.extract(work_sections, use_embeddings=use_embeddings)
    timer.lap("extract_skills", f"{len(skills)} skills")

    exp_text = sections.get("experience", "")
    years = years_of_experience(exp_text)
    edu_label, edu_rank = education_level(sections.get("education", "") or text)
    timer.lap("profile", f"{years} yrs, {edu_label}")

    return ResumeResult(
        raw_text=text,
        masked_text=masked_text,
        sections=work_sections,
        skills=[s.to_dict() for s in skills],
        years_experience=years,
        education_level=edu_label,
        education_rank=edu_rank,
        pages=pages,
        steps=timer.steps,
    )


def process_pdf(pdf_bytes: bytes, bias_aware: bool = True, use_embeddings: bool = True) -> ResumeResult:
    timer = _Timer()
    parsed = extract_text(pdf_bytes)
    detail = f"{parsed.pages} page(s)" + (", two-column layout" if parsed.two_column_pages else "")
    timer.lap("extract_text", detail)
    return process_text(parsed.text, bias_aware, use_embeddings=use_embeddings, pages=parsed.pages, timer=timer)
