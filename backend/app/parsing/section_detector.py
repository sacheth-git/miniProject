"""Split resume text into canonical sections using header regex plus heuristics."""

from __future__ import annotations

import re

SECTION_ALIASES: dict[str, list[str]] = {
    "summary": [
        "summary", "professional summary", "career summary", "profile", "professional profile",
        "about me", "objective", "career objective", "about",
    ],
    "skills": [
        "skills", "technical skills", "key skills", "core skills", "skill set", "skillset",
        "core competencies", "competencies", "technologies", "tech stack", "tools and technologies",
        "tools & technologies", "technical proficiency", "areas of expertise", "expertise",
    ],
    "experience": [
        "experience", "work experience", "professional experience", "employment history",
        "work history", "employment", "internships", "internship", "internship experience",
        "industry experience", "relevant experience",
    ],
    "projects": [
        "projects", "academic projects", "personal projects", "key projects", "project work",
        "major projects", "selected projects", "project experience",
    ],
    "education": [
        "education", "academic background", "academics", "educational qualifications",
        "qualifications", "academic qualifications", "education and training",
    ],
    "certifications": [
        "certifications", "certificates", "certification", "licenses and certifications",
        "courses", "online courses", "trainings", "training", "courses and certifications",
    ],
    "achievements": [
        "achievements", "awards", "honors", "honours", "accomplishments", "awards and achievements",
    ],
    "extracurricular": ["extracurricular activities", "activities", "volunteering", "positions of responsibility"],
    "publications": ["publications", "research", "papers"],
    "languages": ["languages", "languages known"],
    "interests": ["interests", "hobbies", "hobbies and interests"],
}

_ALIAS_TO_SECTION = {alias: sec for sec, aliases in SECTION_ALIASES.items() for alias in aliases}
_HEADER_RE = re.compile(
    r"^\s*(?:[#>\-•*]\s*)?("
    + "|".join(sorted((re.escape(a) for a in _ALIAS_TO_SECTION), key=len, reverse=True))
    + r")\s*[:\-|]?\s*$",
    re.IGNORECASE,
)
# "Skills: Python, SQL" -> header with inline content.
_INLINE_RE = re.compile(
    r"^\s*("
    + "|".join(sorted((re.escape(a) for a in SECTION_ALIASES["skills"]), key=len, reverse=True))
    + r")\s*:\s*(.+)$",
    re.IGNORECASE,
)

CANONICAL_SECTIONS = ("summary", "skills", "experience", "projects", "education", "certifications")


def _match_header(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or len(stripped) > 45 or len(stripped.split()) > 5:
        return None
    m = _HEADER_RE.match(stripped.replace("&amp;", "&"))
    if m:
        return _ALIAS_TO_SECTION[m.group(1).lower()]
    return None


def detect_sections(text: str) -> dict[str, str]:
    """Return {section: text}. Content before the first header goes to 'header'."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in text.splitlines():
        sec = _match_header(line)
        if sec is not None:
            current = sec
            sections.setdefault(current, [])
            continue
        inline = _INLINE_RE.match(line)
        if inline:
            sections.setdefault("skills", []).append(inline.group(2))
            continue
        sections.setdefault(current, []).append(line)
    result = {k: "\n".join(v).strip() for k, v in sections.items()}
    return {k: v for k, v in result.items() if v}
