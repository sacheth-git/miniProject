from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.ingestion.dedup import dedup_jobs
from app.ingestion.link_checker import checkable
from app.skills.jd_skill_weighter import compute_idf, extract_jd_skills, segment_jd, skill_weights
from tests.fakes import FakeEncoder


@dataclass
class J:
    id: str
    source: str
    company_norm: str
    title: str
    description: str
    apply_options: list[dict[str, Any]] = field(default_factory=list)
    posted_at: datetime | None = None
    dedup_group_id: str | None = None
    is_duplicate: bool = False


DESC = "Build data pipelines with Python Spark and Airflow for analytics teams in Bengaluru."


def test_dedup_merges_cross_source_postings() -> None:
    a = J("a", "jsearch", "acme", "Data Engineer", DESC, [{"publisher": "LinkedIn", "url": "https://li/1"}])
    b = J("b", "greenhouse", "acme", "Data Engineer", DESC, [{"publisher": "Acme", "url": "https://gh/1", "is_direct": True}],
          posted_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    c = J("c", "lever", "acme", "Sales Manager", "Sell enterprise software to banks.")
    d = J("d", "jsearch", "other", "Data Engineer", DESC)  # different company: never merged
    stats = dedup_jobs([a, b, c, d], FakeEncoder())
    assert a.dedup_group_id == b.dedup_group_id == "b"  # direct employer source is canonical
    assert b.is_duplicate is False and a.is_duplicate is True
    assert [o["url"] for o in a.apply_options] == ["https://gh/1", "https://li/1"]  # direct first
    assert c.dedup_group_id == "c" and not c.is_duplicate
    assert d.dedup_group_id == "d"
    assert stats["groups_merged"] == 1 and stats["duplicates"] == 1


def test_link_checker_never_touches_job_boards() -> None:
    assert not checkable("https://www.linkedin.com/jobs/view/1")
    assert not checkable("https://www.naukri.com/job-listings-x")
    assert not checkable("https://in.indeed.com/viewjob?jk=1")
    assert checkable("https://boards.greenhouse.io/acme/jobs/1")


JD = """About the role
You will build ML services in Python.
Requirements
- 3+ years with PyTorch and SQL
- Strong Docker skills
Nice to have
- Kubernetes
- Experience with Airflow is a plus
- Must know Git
Benefits
- Free Kafka training
"""


def test_segment_and_extract_jd(phrase_extractor) -> None:  # type: ignore[no-untyped-def]
    modes = dict((line, mode) for mode, line in segment_jd(JD))
    assert modes["- Kubernetes"] == "preferred"
    assert modes["- Must know Git"] == "required"  # cue overrides section
    assert modes["- Free Kafka training"] == "ignore"
    req, pref = extract_jd_skills(JD, phrase_extractor)
    req_names, pref_names = {s.name for s in req}, {s.name for s in pref}
    assert {"Python", "PyTorch", "SQL", "Docker", "Git"} <= req_names
    assert {"Kubernetes", "Apache Airflow"} <= pref_names
    assert "Apache Kafka" not in req_names | pref_names


def test_idf_and_weights() -> None:
    idf = compute_idf([["python", "sql"], ["python"], ["python", "rust"]])
    assert min(idf.values()) == 0.5 and max(idf.values()) == 1.5
    assert idf["python"] == 0.5  # most common -> lowest
    w = skill_weights([{"skill_id": "rust"}], [{"skill_id": "python"}, {"skill_id": "rust"}], idf)
    assert w["rust"] == 1.5  # required wins over preferred
    assert w["python"] == 0.25
    assert compute_idf([]) == {}
    assert compute_idf([["a"], ["a"]]) == {"a": 1.0}
