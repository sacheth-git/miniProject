"""User-provided jobs: pasted JD text, and the user's own job-alert emails (.eml).

Nothing here fetches LinkedIn / Indeed / Naukri pages. Alert emails are parsed
locally; we keep the job title, company and a cleaned link back to the listing.
"""

from __future__ import annotations

import email
import hashlib
import re
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.ingestion.base import ApplyOption, RawJob

MAX_EML_BYTES = 2 * 1024 * 1024

PUBLISHERS = [
    ("linkedin.com", "LinkedIn"),
    ("naukri.com", "Naukri"),
    ("indeed.", "Indeed"),
    ("glassdoor.", "Glassdoor"),
    ("wellfound.com", "Wellfound"),
    ("foundit.in", "foundit"),
    ("instahyre.com", "Instahyre"),
    ("internshala.com", "Internshala"),
    ("greenhouse.io", "Greenhouse"),
    ("lever.co", "Lever"),
    ("ashbyhq.com", "Ashby"),
]
LINKEDIN_JOB = re.compile(r"/(?:comm/)?jobs/view/(\d+)")
NAUKRI_JOB = re.compile(r"naukri\.com/job-listings-[\w-]+")
INDEED_JK = re.compile(r"[?&](?:jk|vjk)=([0-9a-f]{8,})", re.I)
TRACKING_PARAMS = re.compile(r"^(utm_|trk|tracking|refId|trackingId|lipi|midToken|midSig|eid|otpToken|src|from)", re.I)
JOBISH = re.compile(
    r"\b(engineer|developer|intern|internship|analyst|scientist|manager|designer|architect|consultant|"
    r"associate|lead|specialist|administrator|trainee|programmer|tester|sde|devops|researcher)\b",
    re.I,
)
SKIP_ANCHOR = re.compile(r"^(view|apply|see|unsubscribe|manage|help|privacy|terms|settings|more|search)\b", re.I)


def publisher_for(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return next((name for dom, name in PUBLISHERS if dom in host), host.removeprefix("www.") or "Company site")


def clean_job_url(url: str) -> str | None:
    """Canonical listing URL without tracking params; None if not a job link."""
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        return None
    host = u.netloc.lower()
    if "linkedin.com" in host:
        m = LINKEDIN_JOB.search(u.path)
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}/" if m else None
    if "indeed." in host:
        m = INDEED_JK.search(url)
        return f"https://in.indeed.com/viewjob?jk={m.group(1)}" if m else None
    if "naukri.com" in host:
        m = NAUKRI_JOB.search(url)
        return f"https://www.{m.group(0)}" if m else None
    q = {k: v for k, v in parse_qs(u.query).items() if not TRACKING_PARAMS.match(k)}
    return urlunparse((u.scheme, u.netloc, u.path, "", urlencode(q, doseq=True), ""))


def _stable_id(*parts: str) -> str:
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()[:32]


def raw_from_text(title: str | None, company: str | None, text: str, url: str | None, location: str | None) -> RawJob:
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Imported job")
    title = (title or first_line)[:300]
    apply = url or ""
    options = [ApplyOption(publisher_for(url), url, False)] if url else []
    return RawJob(
        source="import",
        source_job_id=_stable_id(url or "", title, text[:2000]),
        title=title,
        company=company or "Unknown company",
        description=text,
        apply_url=apply,
        source_url=url,
        location=location,
        apply_options=options,
    )


@dataclass
class EmailJob:
    title: str
    company: str | None
    url: str
    publisher: str
    context: str


def _body_html(msg: EmailMessage) -> tuple[str | None, str | None]:
    html_part = msg.get_body(preferencelist=("html",))
    text_part = msg.get_body(preferencelist=("plain",))
    html = html_part.get_content() if html_part is not None else None
    text = text_part.get_content() if text_part is not None else None
    return html, text


def parse_alert_email(data: bytes) -> list[EmailJob]:
    """Extract (title, company, link) from a job-alert email the user received."""
    if len(data) > MAX_EML_BYTES:
        raise ValueError("Email file larger than 2 MB")
    msg = email.message_from_bytes(data, policy=policy.default)
    if not isinstance(msg, EmailMessage):
        raise ValueError("Not a valid .eml file")
    html, text = _body_html(msg)
    jobs: dict[str, EmailJob] = {}
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            title = " ".join(a.get_text(" ", strip=True).split())
            url = clean_job_url(str(a["href"]))
            if not url or not title or len(title) > 120 or SKIP_ANCHOR.match(title) or not JOBISH.search(title):
                continue
            # Company / location usually sit in the next text nodes after the title link.
            following = []
            for sib in a.find_all_next(string=True, limit=6):
                s = " ".join(str(sib).split())
                if s and s != title:
                    following.append(s)
            company = following[0][:200] if following else None
            jobs.setdefault(url, EmailJob(title, company, url, publisher_for(url), " | ".join(following[:3])))
    if not jobs and text:
        lines = [ln.strip() for ln in text.splitlines()]
        for i, ln in enumerate(lines):
            for m in re.finditer(r"https?://\S+", ln):
                url = clean_job_url(m.group(0).rstrip(">).,"))
                if not url:
                    continue
                title = next((lines[k] for k in range(i - 1, max(i - 4, -1), -1) if JOBISH.search(lines[k])), None)
                if title:
                    jobs.setdefault(url, EmailJob(title[:300], None, url, publisher_for(url), ""))
    return list(jobs.values())


def raw_from_email_job(ej: EmailJob) -> RawJob:
    return RawJob(
        source="import",
        source_job_id=_stable_id(ej.url),
        title=ej.title,
        company=ej.company or "Unknown company",
        description=f"{ej.title}\n{ej.context}\n(Imported from a {ej.publisher} job-alert email. Open the listing for the full description.)",
        apply_url=ej.url,
        source_url=ej.url,
        apply_options=[ApplyOption(ej.publisher, ej.url, False)],
    )
