"""Bias-aware PII masking before embedding.

Masks: email, phone, URLs/handles, the candidate's name, gender words and
personal-status lines, and institution (college) names.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<![\w/.])\+?\(?\d[\d\s().-]{8,16}\d(?![\w/])")
URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin\.com|github\.com|gitlab\.com|behance\.net|leetcode\.com)/\S+", re.I)
PERSONAL_LINE_RE = re.compile(
    r"^.*\b(date of birth|dob|gender|sex|marital status|nationality|religion|father'?s name|mother'?s name|age)\b\s*[:\-].*$",
    re.I | re.M,
)
GENDER_RE = re.compile(
    r"\b(he|she|him|her|his|hers|himself|herself|male|female|man|woman|men|women|boy|girl|"
    r"sir|madam|husband|wife|son|daughter)\b",
    re.I,
)
# Titles are case-sensitive so "MS Excel" / "MS in CS" survive.
TITLE_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx)\.?(?=\s+[A-Z][a-z])")
INSTITUTION_RE = re.compile(
    r"\b(?:(?:[A-Z][\w.&'-]*|of|and|for|the)\s+){0,7}"
    r"(?:University|Institute|College|Vidyalaya|Vidyapeeth|Academy|Polytechnic|School)"
    r"(?:\s+of(?:\s+(?:[A-Z][\w&'-]*|and|&))+)?"
    r"(?:\s*,\s*[A-Z][a-z]+)?"
    r"|\b(?:IIT|NIT|IIIT|IIM|BITS|VIT|SRM|MIT|RVCE|PESIT?|NITK)\b(?:\s*[,-]?\s*[A-Z][a-z]+)?"
)
NAME_LINE_RE = re.compile(r"^[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,3}$")
NOT_NAME = {"resume", "curriculum", "vitae", "cv", "profile", "summary"}


@dataclass
class MaskResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)
    name: str | None = None


def guess_name(text: str) -> str | None:
    """The first short line of capitalised words is almost always the name."""
    for line in text.splitlines()[:6]:
        line = line.strip()
        if not line:
            continue
        # Matches "Ananya Kulkarni" and "RAVI KUMAR"; masking is case-insensitive.
        if NAME_LINE_RE.match(line) and not (set(line.lower().split()) & NOT_NAME):
            return line
    return None


def _mask_phones(text: str, counts: Counter[str]) -> str:
    """Mask digit runs that look like phone numbers (10-13 digits), not year ranges."""

    def repl(m: re.Match[str]) -> str:
        digits = sum(c.isdigit() for c in m.group(0))
        if 10 <= digits <= 13:
            counts["[PHONE]"] += 1
            return "[PHONE]"
        return m.group(0)

    return PHONE_RE.sub(repl, text)


def mask_pii(text: str, name: str | None = None) -> MaskResult:
    counts: Counter[str] = Counter()

    def sub(pattern: re.Pattern[str], token: str, s: str) -> str:
        new, n = pattern.subn(token, s)
        counts[token] += n
        return new

    name = name or guess_name(text)
    out = sub(PERSONAL_LINE_RE, "[PERSONAL]", text)
    out = sub(EMAIL_RE, "[EMAIL]", out)
    out = sub(URL_RE, "[URL]", out)
    out = _mask_phones(out, counts)
    out = sub(TITLE_RE, "[GENDER]", out)  # before names: the lookahead needs "Ms. Kulkarni"
    if name:
        parts = [p for p in re.split(r"\s+", name) if len(p.strip(".")) >= 3]
        if parts:
            name_re = re.compile(r"\b(" + "|".join(re.escape(p) for p in parts) + r")\b", re.I)
            out = sub(name_re, "[NAME]", out)
            out = re.sub(r"\[NAME\](?:\s+\[NAME\])+", "[NAME]", out)
    out = sub(INSTITUTION_RE, "[INSTITUTION]", out)
    out = sub(GENDER_RE, "[GENDER]", out)
    return MaskResult(text=out, counts={k: v for k, v in counts.items() if v}, name=name)
