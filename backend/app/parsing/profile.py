"""Years of experience from date ranges, and highest education level."""

from __future__ import annotations

import re
from datetime import date

MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december"),
        ]
    )
    for m in names
}
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DATE = rf"(?:{_MONTH}\.?,?\s*'?\d{{2,4}}|\d{{1,2}}\s*[/.-]\s*\d{{4}}|\d{{4}})"
_END = rf"(?:{_DATE}|present|current|now|till\s+date|to\s+date|ongoing|today)"
RANGE_RE = re.compile(rf"({_DATE})\s*(?:-|–|—|to|till|until)\s*({_END})", re.IGNORECASE)


def _parse_date(s: str, today: date, is_end: bool) -> tuple[int, int] | None:
    s = s.strip().lower().replace(",", " ").replace(".", " ").replace("'", "")
    if re.fullmatch(r"present|current|now|till\s+date|to\s+date|ongoing|today", s):
        return today.year, today.month
    m = re.fullmatch(r"([a-z]+)\s*(\d{2,4})", s)
    if m and m.group(1) in MONTHS:
        year = int(m.group(2))
        year = year + 2000 if year < 100 else year
        return year, MONTHS[m.group(1)]
    m = re.fullmatch(r"(\d{1,2})\s*[/-]\s*(\d{4})", s) or re.fullmatch(r"(\d{1,2})\s+(\d{4})", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(2)), int(m.group(1))
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return int(m.group(1)), 12 if is_end else 1
    return None


def date_ranges(text: str, today: date | None = None) -> list[tuple[int, int]]:
    """Return (start_month_index, end_month_index) pairs; month index = year*12 + month."""
    today = today or date.today()
    now_idx = today.year * 12 + today.month
    out: list[tuple[int, int]] = []
    for m in RANGE_RE.finditer(text):
        a = _parse_date(m.group(1), today, is_end=False)
        b = _parse_date(m.group(2), today, is_end=True)
        if not a or not b:
            continue
        start, end = a[0] * 12 + a[1], b[0] * 12 + b[1]
        if not (1970 * 12 <= start <= now_idx + 1) or end < start:
            continue
        out.append((start, min(end, now_idx)))
    return out


def years_of_experience(experience_text: str, today: date | None = None) -> float:
    """Total years covered by date ranges, with overlapping ranges merged."""
    ranges = sorted(date_ranges(experience_text, today))
    total = 0
    cur_s: int | None = None
    cur_e = 0
    for s, e in ranges:
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e + 1:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s + 1
            cur_s, cur_e = s, e
    if cur_s is not None:
        total += cur_e - cur_s + 1
    return round(total / 12, 1)


EDUCATION_LEVELS: list[tuple[str, int, re.Pattern[str]]] = [
    ("phd", 5, re.compile(r"\b(ph\.?\s?d|doctor(?:ate| of philosophy))\b", re.I)),
    (
        "masters",
        4,
        re.compile(
            r"\b(m\.\s?tech|mtech|m\.\s?e\.|m\.\s?sc|msc|m\.\s?s\.|mca|mba|m\.\s?com|pgdm|"
            r"master(?:'s|s)?(?:\s+of|\s+in|\s+degree)|ms\s+in)\b",
            re.I,
        ),
    ),
    (
        "bachelors",
        3,
        re.compile(
            r"\b(b\.\s?tech|btech|b\.\s?e\.|be\s+(?:in|\()|b\.\s?sc|bsc|bca|b\.\s?com|bcom|bba|b\.\s?s\.|"
            r"bachelor(?:'s|s)?(?:\s+of|\s+in|\s+degree)?|undergraduate)",
            re.I,
        ),
    ),
    ("diploma", 2, re.compile(r"\b(diploma|polytechnic)\b", re.I)),
    (
        "higher_secondary",
        1,
        re.compile(r"\b(12th|xii|hsc|puc|pre-university|intermediate|senior secondary|class 12)\b", re.I),
    ),
]


def education_level(text: str) -> tuple[str, int]:
    """Highest education level mentioned: (label, ordinal 0-5)."""
    for label, rank, pat in EDUCATION_LEVELS:
        if pat.search(text):
            return label, rank
    return "unknown", 0
