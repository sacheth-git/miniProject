"""Job-description skills with importance weights.

w_j = type_j * idf_j
  type_j = 1.0 if required, 0.5 if preferred (from cue phrases and section headers)
  idf_j  = log-idf over the active job corpus, min-max normalised to [0.5, 1.5]
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.skills.extractor import SkillExtractor

REQUIRED_TYPE = 1.0
PREFERRED_TYPE = 0.5

PREF_HEADER = re.compile(
    r"^(nice[- ]to[- ]haves?|preferred(?: qualifications| skills)?|bonus(?: points)?|good[- ]to[- ]have|"
    r"pluses|it(?:'|’)?s a plus|desired(?: skills)?|desirable|additional (?:qualifications|skills)|"
    r"extra credit|what would make you stand out|ways to stand out)\b",
    re.I,
)
REQ_HEADER = re.compile(
    r"^(requirements|required(?: qualifications| skills)?|minimum qualifications|basic qualifications|"
    r"qualifications|must[- ]haves?|what you(?:'|’)?ll need|what we(?:'|’)?re looking for|"
    r"who you are|about you|what you bring|skills(?: & | and )?(?:experience|requirements)?|"
    r"responsibilities|key responsibilities|what you(?:'|’)?ll do|the role|your role|job description|"
    r"technical skills|experience)\b",
    re.I,
)
IGNORE_HEADER = re.compile(
    r"^(about us|about the company|who we are|our company|benefits|perks|what we offer|why join|"
    r"compensation|salary|equal opportunity|eeo|diversity|our values|life at|how to apply|"
    r"privacy|disclaimer|location)\b",
    re.I,
)
PREF_CUE = re.compile(
    r"\b(nice to have|good to have|is a plus|are a plus|a plus|bonus|preferred|preferably|desirable|"
    r"ideally|familiarity with|exposure to|nice-to-have|optional|advantageous)\b",
    re.I,
)
REQ_CUE = re.compile(r"\b(must|required|mandatory|essential|need to have|proficien\w*|expert\w*|strong)\b", re.I)


@dataclass
class JDSkill:
    skill_id: str
    name: str
    type: str  # required | preferred
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {"skill_id": self.skill_id, "name": self.name, "type": self.type, "evidence": self.evidence}


def _whole(pattern: re.Pattern[str], s: str) -> bool:
    """Header pattern must cover the whole line (trailing ':' or '.' allowed)."""
    m = pattern.match(s)
    return bool(m) and not s[m.end() :].strip(" :.!").strip()


def _header_mode(line: str) -> str | None:
    raw = line.strip()
    if raw[:1] in {"-", "•", "*", "·"} and not raw.startswith("**"):
        return None  # bullets are content, never headers
    s = raw.strip("#*: ").strip()
    if not s or len(s) > 70 or len(s.split()) > 8:
        return None
    if _whole(PREF_HEADER, s):
        return "preferred"
    if _whole(IGNORE_HEADER, s):
        return "ignore"
    if _whole(REQ_HEADER, s):
        return "required"
    return None


def segment_jd(text: str) -> list[tuple[str, str]]:
    """Split JD text into (mode, line) with mode in required/preferred/ignore.

    Section headers set the mode; a line's own cue phrase overrides it.
    Text before any header counts as required (it usually describes the role).
    """
    mode = "required"
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        hdr = _header_mode(line)
        if hdr is not None:
            mode = hdr
            continue
        line_mode = mode
        if mode != "ignore":
            if PREF_CUE.search(line):
                line_mode = "preferred"
            elif REQ_CUE.search(line) and mode == "preferred":
                line_mode = "required"
        out.append((line_mode, line))
    return out


def extract_jd_skills(text: str, extractor: SkillExtractor) -> tuple[list[JDSkill], list[JDSkill]]:
    """(required, preferred). A skill seen as both counts as required."""
    blocks: dict[str, list[str]] = {"required": [], "preferred": []}
    for mode, line in segment_jd(text):
        if mode in blocks:
            blocks[mode].append(line)
    found: dict[str, JDSkill] = {}
    for mode in ("required", "preferred"):
        if not blocks[mode]:
            continue
        for s in extractor.extract({"jd": "\n".join(blocks[mode])}, use_embeddings=False):
            if s.skill_id in found:
                continue  # required pass ran first
            found[s.skill_id] = JDSkill(s.skill_id, s.name, mode, s.evidence)
    req = [s for s in found.values() if s.type == "required"]
    pref = [s for s in found.values() if s.type == "preferred"]
    return req, pref


def compute_idf(job_skill_ids: Iterable[Iterable[str]]) -> dict[str, float]:
    """Smoothed idf per skill over jobs, min-max normalised to [0.5, 1.5]."""
    df: Counter[str] = Counter()
    n = 0
    for ids in job_skill_ids:
        n += 1
        df.update(set(ids))
    if not df:
        return {}
    raw = {k: math.log((1 + n) / (1 + v)) + 1 for k, v in df.items()}
    lo, hi = min(raw.values()), max(raw.values())
    if hi - lo < 1e-9:
        return {k: 1.0 for k in raw}
    return {k: 0.5 + (v - lo) / (hi - lo) for k, v in raw.items()}


def skill_weights(
    required: list[dict[str, Any]], preferred: list[dict[str, Any]], idf: dict[str, float]
) -> dict[str, float]:
    """skill_id -> w_j = type_j * idf_j (unknown skills get idf 1.0)."""
    w: dict[str, float] = {}
    for s in preferred:
        w[s["skill_id"]] = PREFERRED_TYPE * idf.get(s["skill_id"], 1.0)
    for s in required:
        w[s["skill_id"]] = REQUIRED_TYPE * idf.get(s["skill_id"], 1.0)
    return w
