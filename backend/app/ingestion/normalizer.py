"""RawJob -> normalised job fields: plain text, job type, remote, experience, location."""

from __future__ import annotations

import hashlib
import html as html_lib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from app.ingestion.base import RawJob

COMPANY_SUFFIX = re.compile(
    r"[,.]?\s+\b(inc|inc\.|llc|ltd|ltd\.|limited|pvt|private|corp|corporation|co|company|gmbh|plc|"
    r"technologies|technology|tech|labs|software|solutions|india|global|group|holdings)\b\.?\s*$",
    re.I,
)  # trailing suffixes only, stripped repeatedly: "Acme Labs India Pvt. Ltd." -> "acme"
INDIA_RE = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|pune|hyderabad|chennai|gurugram|gurgaon|noida|delhi|"
    r"new delhi|kolkata|ahmedabad|jaipur|kochi|coimbatore|mysuru|mysore|indore|chandigarh|"
    r"thiruvananthapuram|trivandrum|mangaluru|mangalore|nagpur|bhubaneswar|vadodara|surat|lucknow)\b",
    re.I,
)
REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|anywhere|distributed)\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
INTERN_RE = re.compile(r"\b(intern|internship|interns|trainee|apprentice|co-op|coop)\b", re.I)
CONTRACT_RE = re.compile(r"\b(contract|contractor|temporary|temp|freelance|fixed[- ]term)\b", re.I)
PART_TIME_RE = re.compile(r"\bpart[- ]time\b", re.I)

_YEARS = r"(?:years?|yrs?)"
EXP_RANGE_RE = re.compile(rf"(\d{{1,2}}(?:\.\d)?)\s*(?:\+\s*)?(?:-|–|to)\s*(\d{{1,2}}(?:\.\d)?)\s*\+?\s*{_YEARS}", re.I)
EXP_MIN_RE = re.compile(
    rf"(?:at\s+least|minimum(?:\s+of)?|min\.?|over|more\s+than)?\s*(\d{{1,2}}(?:\.\d)?)\s*\+?\s*(?:\+|plus)?\s*{_YEARS}"
    r"(?:\s+of)?(?:\s+\w+){0,4}?\s+(?:experience|exp\b)",
    re.I,
)
FRESHER_RE = re.compile(r"\b(fresher|freshers|new grad(?:uate)?s?|entry[- ]level|recent graduates?|0\s*years)\b", re.I)
SENIORITY = [
    (re.compile(r"\b(principal|distinguished|director|head of|vp|vice president)\b", re.I), 10.0),
    (re.compile(r"\b(staff|lead|architect|manager)\b", re.I), 7.0),
    (re.compile(r"\b(senior|sr\.?|sde[- ]?(?:iii|3))\b", re.I), 4.0),
    (re.compile(r"\b(junior|jr\.?|associate|graduate|sde[- ]?(?:i|1))\b", re.I), 0.0),
]

RESP_HEADERS = re.compile(
    r"^(responsibilities|key responsibilities|what you(?:'|’)?ll do|what you will do|the role|"
    r"your role|role overview|in this role|day to day|duties|job description|about the role|what you(?:'|’)?ll be doing)\b",
    re.I,
)
OTHER_HEADERS = re.compile(
    r"^(requirements|qualifications|what we(?:'|’)?re looking for|who you are|about you|what you bring|"
    r"skills|must have|nice to have|preferred|bonus|benefits|perks|about us|about the company|why join|"
    r"what we offer|compensation|equal opportunity)\b",
    re.I,
)


@dataclass
class NormalizedJob:
    source: str
    source_job_id: str
    title: str
    company: str
    company_norm: str
    description: str
    responsibilities: str
    location: str | None
    country: str | None
    remote: bool
    job_type: str
    experience_min: float | None
    experience_max: float | None
    posted_at: datetime | None
    apply_url: str
    apply_options: list[dict[str, Any]]
    source_url: str | None
    content_hash: str
    extra: dict[str, Any] = field(default_factory=dict)


def html_to_text(raw: str) -> str:
    """HTML -> text, keeping list items and block boundaries as lines."""
    if not raw:
        return ""
    if "<" not in raw and "&" in raw:
        raw = html_lib.unescape(raw)
    if "<" not in raw:
        text = raw
    else:
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        for li in soup.find_all("li"):
            li.insert_before("\n- ")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        for blk in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "tr", "section"]):
            blk.insert_before("\n")
            blk.insert_after("\n")
        text = soup.get_text()
    text = text.replace(" ", " ").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_company(name: str) -> str:
    n = name.lower().strip()
    prev = None
    while prev != n:
        prev = n
        n = COMPANY_SUFFIX.sub("", n).strip()
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def detect_job_type(title: str, source_type: str | None, text: str) -> str:
    probe = f"{title} {source_type or ''}"
    if INTERN_RE.search(probe):
        return "internship"
    if CONTRACT_RE.search(probe):
        return "contract"
    if PART_TIME_RE.search(probe):
        return "part-time"
    if source_type is None and INTERN_RE.search(text[:400]):
        return "internship"
    return "full-time"


def detect_remote(location: str | None, title: str, flag: bool | None) -> bool:
    if flag is not None:
        return bool(flag)
    probe = f"{location or ''} {title}"
    return bool(REMOTE_RE.search(probe)) and not HYBRID_RE.search(probe)


def detect_country(location: str | None, given: str | None) -> str | None:
    if given:
        g = given.strip()
        return "India" if g.upper() in {"IN", "IND", "INDIA"} else g
    if not location:
        return None
    if INDIA_RE.search(location):
        return "India"
    parts = [p.strip() for p in re.split(r"[,;/|]", location) if p.strip()]
    return parts[-1][:64] if len(parts) >= 2 else None


def extract_experience(
    title: str, text: str, job_type: str, months: int | None = None
) -> tuple[float | None, float | None]:
    """(min_years, max_years). Uses the source value, then text patterns, then title seniority."""
    if months is not None:
        y = round(months / 12, 1)
        return y, None
    if job_type == "internship":
        return 0.0, 1.0
    head = text[:6000]
    m = EXP_RANGE_RE.search(head)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo <= hi <= 30:
            return lo, hi
    mins = [float(x) for x in EXP_MIN_RE.findall(head) if float(x) <= 25]
    if mins:
        return min(mins), None
    if FRESHER_RE.search(head) or FRESHER_RE.search(title):
        return 0.0, 1.0
    for pat, years in SENIORITY:
        if pat.search(title):
            return years, None
    return None, None


def split_responsibilities(text: str) -> str:
    """Text under a responsibilities-style header, up to the next known header."""
    lines = text.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        stripped = line.strip().rstrip(":").strip()
        short = len(stripped) <= 60
        if short and RESP_HEADERS.match(stripped):
            capturing = True
            continue
        if capturing and short and OTHER_HEADERS.match(stripped):
            break
        if capturing:
            out.append(line)
    return "\n".join(out).strip()


def content_hash(*parts: str) -> str:
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()


def normalize(raw: RawJob) -> NormalizedJob:
    text = html_to_text(raw.description)
    job_type = detect_job_type(raw.title, raw.job_type, text)
    exp_min, exp_max = extract_experience(raw.title, text, job_type, raw.experience_months)
    posted = raw.posted_at
    if posted is not None and posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    options = [o.to_dict() for o in raw.apply_options] or [{"publisher": raw.source, "url": raw.apply_url, "is_direct": False}]
    return NormalizedJob(
        source=raw.source,
        source_job_id=raw.source_job_id[:255],
        title=raw.title[:300] or "Untitled role",
        company=(raw.company or "Unknown company")[:200],
        company_norm=normalize_company(raw.company or "unknown")[:200],
        description=text,
        responsibilities=split_responsibilities(text),
        location=(raw.location or None) and raw.location[:400],
        country=detect_country(raw.location, raw.country),
        remote=detect_remote(raw.location, raw.title, raw.remote),
        job_type=job_type,
        experience_min=exp_min,
        experience_max=exp_max,
        posted_at=posted,
        apply_url=raw.apply_url[:2000],
        apply_options=options,
        source_url=(raw.source_url or raw.apply_url)[:2000],
        content_hash=content_hash(raw.title, raw.company, text, raw.apply_url),
        extra=raw.extra,
    )
