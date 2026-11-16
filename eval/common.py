"""Shared evaluation code: role families, proxy labels, synthetic resumes, features, methods, metrics.

Run every eval script from the repo root with the backend venv, e.g.
    backend\\.venv\\Scripts\\python.exe eval\\build_gold.py
"""

from __future__ import annotations

import json
import math
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402

EVAL = ROOT / "eval"
DATA = EVAL / "data"
RESULTS = EVAL / "results"
GOLD = DATA / "gold"

# ---------------------------------------------------------------- role families
# Title patterns decide a job's family. Order matters: first match wins.
FAMILIES: dict[str, str] = {
    "fullstack": r"full[\s-]?stack",
    "ml": r"machine learning|\bml\b|deep learning|computer vision|\bnlp\b|\bai\b engineer|applied scientist|ai/ml|llm",
    "data_sci": r"data scien",
    "data_eng": r"data engineer|\betl\b|big data|analytics engineer|data platform",
    "data_analyst": r"data analyst|business analyst|\banalytics\b|\bbi\b|business intelligence|insights analyst",
    "devops": r"devops|site reliability|\bsre\b|cloud engineer|infrastructure engineer|platform engineer",
    "qa": r"\bqa\b|quality assurance|test engineer|\bsdet\b|automation test|quality engineer",
    "frontend": r"front[\s-]?end|\bui engineer|react developer|web developer",
    "backend": r"back[\s-]?end|\bapi\b engineer|server engineer|java developer|python developer|golang|node(\.js)? developer",
    "embedded": r"embedded|firmware|vlsi|asic|fpga|hardware engineer|electronics",
    "mech": r"mechanical|cad engineer|design engineer|manufacturing|production engineer|automotive|graduate engineer trainee",
    "swe": r"software engineer|software developer|\bsde\b|developer|programmer",
}
ADJACENT: dict[str, set[str]] = {
    "ml": {"data_sci", "data_eng"}, "data_sci": {"ml", "data_analyst", "data_eng"},
    "data_analyst": {"data_sci", "data_eng"}, "data_eng": {"data_sci", "backend", "ml", "data_analyst"},
    "backend": {"fullstack", "devops", "data_eng", "qa"}, "frontend": {"fullstack"},
    "fullstack": {"backend", "frontend"}, "devops": {"backend"}, "qa": {"backend"},
    "embedded": set(), "mech": set(),
}
GENERIC_SWE_FIT = {"backend": 2, "fullstack": 2, "frontend": 1, "devops": 1, "ml": 1, "qa": 1}
SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|manager|director|head|vp|architect|ii+|iii|iv)\b", re.I)


def job_family(title: str) -> str | None:
    t = title.lower()
    for fam, pat in FAMILIES.items():
        if re.search(pat, t):
            return fam
    return None


def proxy_label(resume_family: str, job_title: str) -> int:
    """0-3 relevance from the job TITLE only (independent of every ranking method).

    3 same family at an entry/mid level, 2 generic software title for a software family,
    1 adjacent family or a senior same-family role, 0 unrelated.
    """
    fam = job_family(job_title)
    senior = bool(SENIOR.search(job_title))
    if fam == resume_family:
        return 1 if senior else 3
    if fam == "swe" and resume_family in GENERIC_SWE_FIT:
        return min(GENERIC_SWE_FIT[resume_family], 1 if senior else 3)
    if fam in ADJACENT.get(resume_family, set()):
        return 1
    return 0


# ---------------------------------------------------------------- synthetic resumes
ROLE_SPECS: dict[str, dict[str, Any]] = {
    "ml": {"title": "Machine Learning Engineer", "core": ["Python", "Machine Learning", "Deep Learning", "PyTorch", "TensorFlow", "scikit-learn", "NumPy", "Pandas", "NLP", "Computer Vision"],
           "extra": ["SQL", "Docker", "Git", "OpenCV", "Hugging Face", "MLflow"],
           "projects": ["Trained a {0} model in {1} to classify customer reviews with 89% accuracy", "Built an image segmentation pipeline using {0} and {1}", "Deployed a {0} model behind a REST API with {1}"]},
    "data_sci": {"title": "Data Scientist", "core": ["Python", "Statistics", "Machine Learning", "Pandas", "scikit-learn", "SQL", "A/B Testing", "Data Visualization", "Regression"],
                 "extra": ["R", "Tableau", "Spark", "XGBoost", "Jupyter"],
                 "projects": ["Built a churn prediction model with {0} and {1}, lifting retention 6%", "Ran A/B tests and causal analysis using {0} and {1}", "Forecasted weekly demand using {0} time series models and {1}"]},
    "data_analyst": {"title": "Data Analyst", "core": ["SQL", "Microsoft Excel", "Power BI", "Tableau", "Data Analysis", "Data Visualization", "Python", "Pandas"],
                     "extra": ["Statistics", "Google Analytics", "Looker", "KPI Reporting"],
                     "projects": ["Built {0} dashboards tracking sales KPIs across 40 stores", "Automated monthly reporting in {0} and {1}, saving 10 hours a month", "Analysed funnel drop-offs with {0} and presented findings in {1}"]},
    "data_eng": {"title": "Data Engineer", "core": ["Python", "SQL", "Apache Spark", "Apache Airflow", "ETL", "Data Pipelines", "Apache Kafka", "AWS"],
                 "extra": ["Docker", "dbt", "Snowflake", "PostgreSQL", "Databricks"],
                 "projects": ["Built batch {0} pipelines orchestrated in {1} processing 2M rows a day", "Streamed events with {0} into a {1} warehouse", "Migrated legacy ETL to {0} with {1}"]},
    "backend": {"title": "Backend Developer", "core": ["Java", "Spring Boot", "Python", "Django", "REST APIs", "PostgreSQL", "MySQL", "Microservices", "Redis"],
                "extra": ["Docker", "Kubernetes", "Git", "AWS", "Apache Kafka"],
                "projects": ["Designed {0} microservices with {1} handling 500 requests per second", "Built a REST API in {0} backed by {1}", "Cut API latency 40% with {0} caching and {1} indexes"]},
    "frontend": {"title": "Frontend Developer", "core": ["JavaScript", "TypeScript", "React", "HTML", "CSS", "Redux", "Next.js", "Tailwind CSS"],
                 "extra": ["Jest", "Figma", "Webpack", "Git"],
                 "projects": ["Built a {0} dashboard in {1} used by 300 merchants", "Converted Figma designs into responsive pages with {0} and {1}", "Improved Lighthouse score from 60 to 95 using {0} and {1}"]},
    "fullstack": {"title": "Full Stack Developer", "core": ["JavaScript", "React", "Node.js", "Express.js", "MongoDB", "REST APIs", "HTML", "CSS", "TypeScript"],
                  "extra": ["Docker", "AWS", "PostgreSQL", "Redux", "Git"],
                  "projects": ["Built a MERN app with {0} and {1} and JWT auth", "Shipped a booking platform with {0} front end and {1} APIs", "Added real-time chat using {0} and {1}"]},
    "devops": {"title": "DevOps Engineer", "core": ["Docker", "Kubernetes", "Terraform", "AWS", "CI/CD", "Linux", "Jenkins", "Ansible", "Prometheus"],
               "extra": ["Python", "Bash", "Grafana", "Helm", "GitHub Actions"],
               "projects": ["Automated infrastructure with {0} and {1} across three environments", "Built {0} pipelines that cut release time from days to hours using {1}", "Set up monitoring with {0} and {1}"]},
    "embedded": {"title": "Embedded Software Engineer", "core": ["Embedded C", "C", "Microcontrollers", "RTOS", "STM32", "I2C", "SPI", "UART", "Firmware Development"],
                 "extra": ["Python", "Verilog", "FPGA", "Arduino", "Oscilloscope", "PCB Design"],
                 "projects": ["Wrote {0} firmware for an {1} sensor board", "Ported a {0} scheduler to {1}", "Built an IoT node with {0} and {1} reporting to the cloud"]},
    "mech": {"title": "Mechanical Design Engineer", "core": ["SolidWorks", "AutoCAD", "CATIA", "ANSYS", "GD&T", "Finite Element Analysis", "Computational Fluid Dynamics", "Creo"],
             "extra": ["MATLAB", "Six Sigma", "Lean Manufacturing", "3D Printing"],
             "projects": ["Designed a gearbox housing in {0} and validated it with {1}", "Reduced bracket weight 15% using {0} and {1}", "Ran {0} on a heat exchanger and compared it with {1}"]},
}
FIRST = ["Aarav", "Diya", "Kabir", "Isha", "Rohan", "Meera", "Arjun", "Ananya", "Vivaan", "Kavya", "Nikhil", "Sneha", "Rahul", "Priya", "Aditya", "Tanvi"]
LAST = ["Rao", "Iyer", "Shetty", "Nair", "Kulkarni", "Hegde", "Reddy", "Menon", "Joshi", "Patil"]
COMPANIES = ["Arcadia Labs", "Bluestem Systems", "Copperleaf Tech", "Driftwood Analytics", "Elmstone Works"]
CSS = "* { font-family: sans-serif; font-size: 9.5pt; line-height: 1.3; } h1 { font-size: 16pt; margin: 0; } h2 { font-size: 11pt; margin: 8pt 0 2pt 0; border-bottom: 1px solid #888; } p, li { margin: 0 0 2pt 0; } ul { margin: 0 0 0 12pt; padding: 0; }"


@dataclass
class GoldResume:
    id: str
    family: str
    name: str
    years: int
    skills: list[str]
    pdf: Path


def make_resume_pdf(rng: random.Random, rid: str, family: str) -> GoldResume:
    import fitz

    spec = ROLE_SPECS[family]
    core = rng.sample(spec["core"], rng.randint(5, min(8, len(spec["core"]))))
    extra = rng.sample(spec["extra"], rng.randint(1, 3))
    skills = core + extra
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    years = rng.choice([0, 0, 1, 2, 3])
    projects = [t.format(*rng.sample(skills, 3)) for t in rng.sample(spec["projects"], 2)]
    exp = ""
    if years:
        co = rng.choice(COMPANIES)
        exp = (f"<h2>Experience</h2><p><b>{spec['title']}</b>, {co} (Jan {2026 - years} - Present)</p>"
               f"<ul><li>Built and shipped features using {skills[0]} and {skills[1]}.</li>"
               f"<li>Improved reliability and cut processing time by 30% with {skills[2]}.</li></ul>")
    else:
        exp = (f"<h2>Internship</h2><p><b>{spec['title']} Intern</b>, {rng.choice(COMPANIES)} (Jun 2025 - Aug 2025)</p>"
               f"<ul><li>Worked with {skills[0]} and {skills[1]} on an internal tool.</li></ul>")
    body = (f"<h1>{name}</h1><p>{name.split()[0].lower()}.{rid}@example.com | +91 98{rng.randint(10000000, 99999999)}</p>"
            f"<h2>Summary</h2><p>Aspiring {spec['title']} with hands-on work in {skills[0]} and {skills[1]}.</p>"
            f"<h2>Skills</h2><p>{', '.join(skills)}</p>{exp}"
            f"<h2>Projects</h2><ul>{''.join(f'<li>{p}.</li>' for p in projects)}</ul>"
            f"<h2>Education</h2><p>B.E. in Engineering, Example Institute of Technology (2021 - 2025), CGPA {rng.uniform(6.8, 9.4):.2f}</p>")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_htmlbox(fitz.Rect(40, 40, 555, 802), f"<html><body>{body}</body></html>", css=CSS)
    path = DATA / "resumes" / f"{rid}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    return GoldResume(rid, family, name, years, skills, path)


# ---------------------------------------------------------------- loading
def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")


def candidate_from_parsed(rec: dict[str, Any]):  # type: ignore[no-untyped-def]
    """An in-memory Candidate (never written to the DB) from a parsed resume record."""
    from app.models.candidate import Candidate

    return Candidate(id=rec["id"], filename=rec["id"], raw_text=rec["raw_text"], masked_text=rec["masked_text"],
                     sections=rec["sections"], skills=rec["skills"], years_experience=rec["years_experience"],
                     education_level=rec["education_level"], education_rank=rec["education_rank"],
                     bias_aware=rec["bias_aware"], preferences={}, pages=1)


# ---------------------------------------------------------------- features & methods
@dataclass
class PairFeatures:
    """Per (resume, job) components under several scorer configurations, so ablations and
    weight learning are recombinations of stored numbers."""

    sem: np.ndarray
    sem_full: np.ndarray
    skill: dict[str, np.ndarray] = field(default_factory=dict)  # config name -> skill score
    penalty: dict[str, np.ndarray] = field(default_factory=dict)
    context: np.ndarray | None = None
    raw_sem_full: np.ndarray | None = None  # uncalibrated full-doc cosine (sbert_whole)
    raw_sem: np.ndarray | None = None  # uncalibrated section score


SKILL_CONFIGS = {
    "full": {},
    "no_idf": {"use_idf": False},
    "no_type": {"use_type_weights": False},
    "flat": {"use_idf": False, "use_type_weights": False},
    "hard": {"soft_skill_match": False},
    "no_shrink": {"skill_shrinkage": False},
    "no_cal": {"calibrate": False},
}


def ranks_desc(scores: np.ndarray) -> np.ndarray:
    return np.argsort(-scores, kind="stable")


# ---------------------------------------------------------------- metrics
REL = 2  # labels >= 2 count as relevant for binary metrics


def precision_at(order: np.ndarray, labels: np.ndarray, k: int) -> float:
    return float((labels[order[:k]] >= REL).mean())


def recall_at(order: np.ndarray, labels: np.ndarray, k: int) -> float:
    total = int((labels >= REL).sum())
    return float((labels[order[:k]] >= REL).sum() / total) if total else 0.0


def mrr(order: np.ndarray, labels: np.ndarray) -> float:
    hits = np.where(labels[order] >= REL)[0]
    return float(1.0 / (hits[0] + 1)) if hits.size else 0.0


def ndcg_at(order: np.ndarray, labels: np.ndarray, k: int) -> float:
    gains = (2.0 ** labels[order[:k]] - 1) / np.log2(np.arange(2, min(k, len(order)) + 2))
    ideal = np.sort(labels)[::-1][:k]
    idcg = ((2.0 ** ideal - 1) / np.log2(np.arange(2, len(ideal) + 2))).sum()
    return float(gains.sum() / idcg) if idcg > 0 else 0.0


METRICS = ("P@5", "P@10", "R@10", "MRR", "NDCG@10")


def all_metrics(scores: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    o = ranks_desc(scores)
    return {"P@5": precision_at(o, labels, 5), "P@10": precision_at(o, labels, 10), "R@10": recall_at(o, labels, 10),
            "MRR": mrr(o, labels), "NDCG@10": ndcg_at(o, labels, 10)}


def kendall_tau(a: np.ndarray, b: np.ndarray) -> float:
    from scipy.stats import kendalltau

    t = kendalltau(a, b).statistic
    return 0.0 if t is None or math.isnan(t) else float(t)
