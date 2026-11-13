"""Search deep links for job boards we never scrape (LinkedIn, Naukri, Indeed).

The user clicks through to the board's own search page with the query prefilled.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote_plus, urlencode

ROLE_HINTS: list[tuple[set[str], str]] = [
    ({"Machine Learning", "Deep Learning", "PyTorch", "TensorFlow"}, "Machine Learning Engineer"),
    ({"Natural Language Processing", "Large Language Models", "Computer Vision"}, "AI Engineer"),
    ({"Power BI", "Tableau", "Data Analysis", "Microsoft Excel"}, "Data Analyst"),
    ({"Pandas", "Statistics", "scikit-learn"}, "Data Scientist"),
    ({"Apache Spark", "Apache Airflow", "ETL", "Data Pipelines"}, "Data Engineer"),
    ({"React", "Angular", "Vue.js", "Next.js"}, "Frontend Developer"),
    ({"Node.js", "Django", "Spring Boot", "FastAPI", "Express.js"}, "Backend Developer"),
    ({"Docker", "Kubernetes", "Terraform", "CI/CD"}, "DevOps Engineer"),
    ({"Android Development", "Flutter", "React Native", "Kotlin"}, "Mobile Developer"),
    ({"Embedded C", "Microcontrollers", "RTOS", "Embedded Systems"}, "Embedded Engineer"),
    ({"VLSI", "Verilog", "FPGA"}, "VLSI Engineer"),
    ({"SolidWorks", "AutoCAD", "CATIA", "ANSYS"}, "Mechanical Design Engineer"),
    ({"Selenium", "Automation Testing", "Manual Testing"}, "QA Engineer"),
    ({"Penetration Testing", "Cybersecurity", "Network Security"}, "Security Analyst"),
]


@dataclass
class DeepLink:
    platform: str
    label: str
    url: str


def infer_role(skill_names: list[str]) -> str:
    have = set(skill_names)
    best = max(ROLE_HINTS, key=lambda rh: len(rh[0] & have))
    return best[1] if best[0] & have else "Software Engineer"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def linkedin(keywords: str, location: str | None, internship: bool, remote: bool) -> str:
    q: dict[str, str] = {"keywords": keywords}
    if location:
        q["location"] = location
    if internship:
        q["f_E"] = "1"  # experience level: internship
    if remote:
        q["f_WT"] = "2"  # workplace type: remote
    return "https://www.linkedin.com/jobs/search/?" + urlencode(q)


def naukri(keywords: str, location: str | None, years: float | None) -> str:
    path = _slug(keywords) + "-jobs" + (f"-in-{_slug(location)}" if location else "")
    q: dict[str, str] = {"k": keywords}
    if location:
        q["l"] = location
    if years is not None:
        q["experience"] = str(int(years))
    return f"https://www.naukri.com/{path}?" + urlencode(q)


def indeed(keywords: str, location: str | None, internship: bool) -> str:
    q = {"q": keywords + (" internship" if internship else ""), "l": location or "India"}
    return "https://in.indeed.com/jobs?" + urlencode(q, quote_via=quote_plus)


def build_deeplinks(
    skills: list[str], preferences: dict[str, Any] | None, years_experience: float
) -> dict[str, Any]:
    prefs = preferences or {}
    role = prefs.get("target_role") or infer_role(skills)
    locations = prefs.get("locations") or []
    location = locations[0] if locations else None
    types = prefs.get("job_types") or []
    internship = "internship" in types or (not types and years_experience < 1)
    remote = bool(prefs.get("remote_ok")) and not location
    top = [s for s in skills[:3] if s.lower() not in role.lower()]
    queries = [role] + ([f"{role} {top[0]}"] if top else [])

    links: list[DeepLink] = []
    for q in queries:
        links.append(DeepLink("LinkedIn", q, linkedin(q, location, internship, remote)))
        links.append(DeepLink("Naukri", q, naukri(q, location, years_experience)))
        links.append(DeepLink("Indeed", q, indeed(q, location, internship)))
    return {
        "role": role,
        "location": location,
        "internship": internship,
        "keywords": queries,
        "links": [asdict(link) for link in links],
    }
