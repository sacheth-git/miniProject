from datetime import datetime

import pytest

from app.ingestion.base import ApplyOption, RawJob
from app.ingestion.normalizer import (
    detect_country,
    detect_job_type,
    detect_remote,
    extract_experience,
    html_to_text,
    normalize,
    normalize_company,
    split_responsibilities,
)


def test_html_to_text_keeps_structure() -> None:
    html = "<h2>Requirements</h2><ul><li>Python</li><li>SQL &amp; Spark</li></ul><p>Apply&nbsp;now<br>today</p><script>x()</script>"
    t = html_to_text(html)
    assert "- Python\n- SQL & Spark" in t
    assert "Apply now\ntoday" in t
    assert "x()" not in t
    # Greenhouse sends entity-escaped HTML
    assert "- Go" in html_to_text("&lt;ul&gt;&lt;li&gt;Go&lt;/li&gt;&lt;/ul&gt;".replace("&lt;", "<").replace("&gt;", ">"))
    assert html_to_text("") == ""
    assert html_to_text("plain &amp; simple") == "plain & simple"


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("Stripe, Inc.", "stripe"),
        ("Acme Labs India Pvt. Ltd.", "acme"),
        ("Tech Mahindra", "tech mahindra"),
        ("Razorpay Software Private Limited", "razorpay"),
    ],
)
def test_normalize_company(raw: str, norm: str) -> None:
    assert normalize_company(raw) == norm


def test_job_type() -> None:
    assert detect_job_type("Software Engineer Intern", None, "") == "internship"
    assert detect_job_type("Engineer", "Contract", "") == "contract"
    assert detect_job_type("Engineer", "Part-time", "") == "part-time"
    assert detect_job_type("Engineer", "Full-time", "intern mentor program") == "full-time"
    assert detect_job_type("Engineer", None, "This internship runs 6 months") == "internship"


def test_remote_and_country() -> None:
    assert detect_remote("Remote - India", "SWE", None) is True
    assert detect_remote("Hybrid Remote, Pune", "SWE", None) is False
    assert detect_remote("Bengaluru", "SWE", True) is True
    assert detect_country("Bengaluru, Karnataka", None) == "India"
    assert detect_country("Austin, TX, United States", None) == "United States"
    assert detect_country("Remote", None) is None
    assert detect_country(None, "IN") == "India"


@pytest.mark.parametrize(
    ("title", "text", "jt", "expected"),
    [
        ("Engineer", "We need 3-5 years of experience in Go.", "full-time", (3.0, 5.0)),
        ("Engineer", "Minimum 2+ years of relevant experience.", "full-time", (2.0, None)),
        ("Engineer", "Freshers welcome!", "full-time", (0.0, 1.0)),
        ("Senior Software Engineer", "Build things.", "full-time", (4.0, None)),
        ("Staff Engineer", "", "full-time", (7.0, None)),
        ("Engineer", "", "internship", (0.0, 1.0)),
        ("Engineer", "Nothing here", "full-time", (None, None)),
    ],
)
def test_extract_experience(title: str, text: str, jt: str, expected: tuple) -> None:  # type: ignore[type-arg]
    assert extract_experience(title, text, jt) == expected


def test_extract_experience_from_source_months() -> None:
    assert extract_experience("x", "", "full-time", months=30) == (2.5, None)


def test_split_responsibilities() -> None:
    text = "About us\nWe are great\nWhat you'll do:\n- Build APIs\n- Ship features\nRequirements\n- Python"
    assert split_responsibilities(text) == "- Build APIs\n- Ship features"
    assert split_responsibilities("no headers") == ""


def test_normalize_full() -> None:
    raw = RawJob(
        source="greenhouse",
        source_job_id="acme:1",
        title="Machine Learning Intern",
        company="Acme Labs Pvt Ltd",
        description="<p>Responsibilities</p><ul><li>Train models</li></ul>",
        apply_url="https://boards.greenhouse.io/acme/jobs/1",
        location="Bengaluru, India",
        posted_at=datetime(2026, 10, 1),
        apply_options=[ApplyOption("Acme careers", "https://boards.greenhouse.io/acme/jobs/1", True)],
    )
    n = normalize(raw)
    assert n.job_type == "internship"
    assert n.company_norm == "acme"
    assert n.country == "India"
    assert n.remote is False
    assert n.experience_min == 0.0
    assert n.posted_at is not None and n.posted_at.tzinfo is not None
    assert n.responsibilities == "- Train models"
    assert n.apply_options[0]["is_direct"] is True
    assert len(n.content_hash) == 40


def test_normalize_defaults_apply_option() -> None:
    raw = RawJob("x", "1", "Dev", "", "desc", "https://e.com/1")
    n = normalize(raw)
    assert n.company == "Unknown company"
    assert n.apply_options == [{"publisher": "x", "url": "https://e.com/1", "is_direct": False}]
