"""Seed a demo campus: 1 institution, 1 TPO, 120 synthetic students with generated resumes, 6 drives.

Everything is synthetic: student names are random first/last-name combinations, companies are
fictional. Re-running replaces only the demo institution and its @demo.skillmatch.example accounts.

Usage (from backend/): .\\.venv\\Scripts\\python.exe scripts\\seed_demo.py [--students 120] [--seed 7]
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.auth.security import hash_password  # noqa: E402
from app.campus.bulk_import import warm_profile  # noqa: E402
from app.campus.drives import extract_drive_skills  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.models.campus import Drive, DriveApplication, EligibilityRule  # noqa: E402
from app.models.candidate import Candidate  # noqa: E402
from app.models.user import Institution, StudentProfile, User  # noqa: E402
from app.services import resume_store  # noqa: E402
from app.services.resume_pipeline import process_pdf  # noqa: E402

INSTITUTION = "Westfield Institute of Technology (Demo)"
INST_CODE = "WITDEMO"
INVITE = "WITDEMO1"
DOMAIN = "demo.skillmatch.example"  # users are <name>.<n>@demo.skillmatch.example (reserved .example domain)
PASSWORD = "Demo@2026"
TPO_EMAIL = "tpo@demo.skillmatch.example"

MALE = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karthik", "Siddharth", "Rahul", "Nikhil", "Pranav", "Varun",
        "Manish", "Harsha", "Akash", "Suraj", "Tejas", "Yash", "Deepak", "Gautam", "Kiran"]
FEMALE = ["Ananya", "Diya", "Isha", "Kavya", "Meera", "Nisha", "Priya", "Riya", "Sneha", "Tanvi", "Aditi", "Bhavana",
          "Divya", "Pooja", "Shreya", "Swathi", "Lakshmi", "Neha", "Sanjana", "Varsha"]
LAST = ["Rao", "Shetty", "Iyer", "Nair", "Kulkarni", "Hegde", "Reddy", "Menon", "Joshi", "Patil", "Bhat", "Pai",
        "Sharma", "Verma", "Gowda", "Naidu", "Desai", "Kamath", "Pillai", "Acharya"]

BRANCH_SKILLS: dict[str, list[str]] = {
    "CSE": ["Python", "Java", "C++", "JavaScript", "TypeScript", "SQL", "React", "Node.js", "Django", "Flask",
            "Spring Boot", "REST APIs", "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "scikit-learn",
            "Pandas", "NumPy", "NLP", "OpenCV", "Git", "Docker", "Kubernetes", "AWS", "Linux", "MongoDB",
            "PostgreSQL", "MySQL", "Data Structures", "Algorithms", "OOP"],
    "IT": ["Python", "Java", "JavaScript", "SQL", "HTML", "CSS", "React", "Angular", "Node.js", "Express.js",
           "MongoDB", "MySQL", "REST APIs", "Git", "Docker", "AWS", "Linux", "Power BI", "Tableau", "Pandas",
           "Data Analysis", "Selenium", "Manual Testing", "Data Structures", "Algorithms"],
    "ECE": ["Embedded C", "C", "Python", "MATLAB", "Verilog", "VHDL", "Arduino", "STM32", "ESP32", "Raspberry Pi",
            "I2C", "SPI", "UART", "FPGA", "VLSI", "Xilinx Vivado", "Cadence", "Signal Processing", "PCB Design",
            "KiCad", "IoT", "RTOS", "ModelSim", "LTspice"],
    "EEE": ["MATLAB", "Simulink", "Power Electronics", "Power Systems", "Electrical Machines", "PLC", "SCADA",
            "Control Systems", "Renewable Energy", "Electric Vehicles", "AutoCAD", "Embedded C", "Arduino",
            "LabVIEW", "Python", "Instrumentation"],
    "MECH": ["AutoCAD", "SolidWorks", "CATIA", "ANSYS", "Creo", "Fusion 360", "MATLAB", "GD&T",
             "Finite Element Analysis", "Computational Fluid Dynamics", "CNC Programming", "3D Printing",
             "Lean Manufacturing", "Six Sigma", "HVAC", "Python"],
}
CROSSOVER = ["Python", "Machine Learning", "SQL", "Data Analysis", "Git"]
DEGREE = {"CSE": "Computer Science and Engineering", "IT": "Information Technology", "ECE": "Electronics and Communication Engineering",
          "EEE": "Electrical and Electronics Engineering", "MECH": "Mechanical Engineering"}
PROJECTS: dict[str, list[str]] = {
    "CSE": ["Built a {0} model in {1} to classify support tickets", "Developed a {0} web app with {1} and deployed it on {2}",
            "Implemented a recommendation engine using {0} and {1}", "Created a REST API in {0} backed by {1}"],
    "IT": ["Built an inventory dashboard in {0} using {1}", "Developed an e-commerce site with {0} and {1}",
           "Automated regression tests with {0} for a {1} app", "Analysed sales data with {0} and visualised it in {1}"],
    "ECE": ["Designed an {0} based home automation system with {1}", "Implemented a UART to {0} bridge on an {1}",
            "Simulated a FIR filter in {0} and verified it in {1}", "Built an IoT weather station with {0} and {1}"],
    "EEE": ["Modelled a solar MPPT controller in {0} and {1}", "Designed a PLC ladder program for a {0} conveyor using {1}",
            "Built a battery management prototype with {0} and {1}", "Studied power quality using {0} and {1}"],
    "MECH": ["Designed a gearbox housing in {0} and validated it with {1}", "Ran {0} on a heat exchanger and compared with {1}",
             "Reduced bracket weight 15% using {0} and {1}", "Prototyped a fixture with {0} and {1}"],
}
INTERN_ROLES = {"CSE": "Software Engineering Intern", "IT": "Web Development Intern", "ECE": "Embedded Systems Intern",
                "EEE": "Electrical Design Intern", "MECH": "Design Engineering Intern"}
FAKE_COMPANIES = ["Arcadia Labs", "Bluestem Systems", "Copperleaf Tech", "Driftwood Analytics", "Elmstone Works"]

DRIVES = [
    dict(company="Nimbus Analytics", role="Machine Learning Engineer", job_type="fte", ctc_lpa=9.5, location="Bengaluru",
         category="regular", rounds=["Online test", "Technical interview", "HR interview"],
         rules=dict(allowed_branches=["CSE", "IT", "ECE"], batch_years=[2026], min_cgpa=7.0, max_active_backlogs=0),
         jd="""About the role
Nimbus builds forecasting products for retail. You will train and ship models with our data team.
Responsibilities
- Build machine learning models in Python with scikit-learn and PyTorch
- Write SQL to prepare training data and evaluate models
- Deploy models as REST APIs with Docker
Requirements
- Python, SQL, Machine Learning
- Deep Learning with PyTorch or TensorFlow
- Pandas and NumPy
Nice to have
- NLP, AWS, Git"""),
    dict(company="Kaveri Systems", role="Embedded Software Engineer", job_type="fte", ctc_lpa=6.5, location="Mysuru",
         category="regular", rounds=["Aptitude test", "Technical interview", "HR"],
         rules=dict(allowed_branches=["ECE", "EEE", "CSE"], batch_years=[2026], min_cgpa=6.5, max_active_backlogs=0),
         jd="""Responsibilities
- Write firmware in Embedded C for STM32 and ESP32 boards
- Bring up sensors over I2C, SPI and UART
- Debug with oscilloscopes and logic analysers
Requirements
- Embedded C, Microcontrollers, RTOS
- I2C, SPI, UART
Nice to have
- Python scripting, PCB Design, IoT"""),
    dict(company="BlueOrbit Software", role="Full Stack Developer", job_type="fte", ctc_lpa=7.0, location="Pune",
         category="regular", rounds=["Coding test", "Technical interview", "Managerial", "HR"],
         rules=dict(allowed_branches=["CSE", "IT"], batch_years=[2026], min_cgpa=6.5, max_active_backlogs=0, min_tenth=60, min_twelfth=60),
         jd="""What you'll do
- Build React front ends and Node.js services
- Design REST APIs and MongoDB or MySQL schemas
- Write tests and ship through CI/CD
Requirements
- JavaScript, React, Node.js, REST APIs
- SQL or MongoDB, Git
Nice to have
- TypeScript, Docker, AWS"""),
    dict(company="Deccan Motors", role="Graduate Engineer Trainee (Design)", job_type="fte", ctc_lpa=5.5, location="Chennai",
         category="regular", rounds=["Written test", "Technical interview", "HR"],
         rules=dict(allowed_branches=["MECH", "EEE"], batch_years=[2026], min_cgpa=6.0, max_active_backlogs=1),
         jd="""Responsibilities
- Create 3D models and drawings in SolidWorks or CATIA following GD&T
- Run structural analysis in ANSYS
- Support lean manufacturing projects on the shop floor
Requirements
- AutoCAD, SolidWorks or CATIA, GD&T
- Finite Element Analysis
Nice to have
- Computational Fluid Dynamics, Six Sigma, MATLAB"""),
    dict(company="Lakeview FinTech", role="Data Scientist", job_type="fte", ctc_lpa=18.0, location="Hyderabad",
         category="dream", rounds=["Online assessment", "Case study", "Technical interview", "Director interview"],
         rules=dict(allowed_branches=["CSE", "IT"], batch_years=[2026], min_cgpa=8.0, max_history_backlogs=0),
         jd="""The role
Model credit risk and fraud for a digital lender.
Responsibilities
- Build classification and time series models in Python
- Run A/B tests and explain results to product teams
- Own data pipelines in SQL
Requirements
- Python, SQL, Machine Learning, Statistics
- scikit-learn, Pandas
Nice to have
- Deep Learning, Spark, Tableau"""),
    dict(company="Voltedge Semiconductors", role="VLSI Design Intern (PPO)", job_type="intern+ppo", ctc_lpa=12.0,
         stipend_month=40000, location="Bengaluru", category="regular", rounds=["Online test", "Technical interview"],
         rules=dict(allowed_branches=["ECE", "EEE"], batch_years=[2027], min_cgpa=7.5, max_active_backlogs=0),
         jd="""Six-month internship with a pre-placement offer for strong performers.
Responsibilities
- Write RTL in Verilog and verify it in ModelSim
- Run synthesis on FPGA prototypes with Xilinx Vivado
Requirements
- Verilog, Digital Design, FPGA
Nice to have
- VLSI, Cadence, Python"""),
]

CSS = "* { font-family: sans-serif; font-size: 9.5pt; line-height: 1.3; } h1 { font-size: 17pt; margin: 0; } h2 { font-size: 11pt; margin: 8pt 0 2pt 0; border-bottom: 1px solid #888; } p, li { margin: 0 0 2pt 0; } ul { margin: 0 0 0 12pt; padding: 0; }"


def resume_pdf(rng: random.Random, name: str, email: str, branch: str, cgpa: float, batch: int) -> tuple[bytes, list[str]]:
    pool = BRANCH_SKILLS[branch]
    k = rng.randint(6, min(12, len(pool)))
    skills = rng.sample(pool, k)
    if branch not in ("CSE", "IT") and rng.random() < 0.25:
        skills += [s for s in rng.sample(CROSSOVER, 2) if s not in skills]
    proj_tpls = rng.sample(PROJECTS[branch], 2)
    projects = [t.format(*rng.sample(skills, 3)) for t in proj_tpls]
    exp_html = ""
    if rng.random() < 0.45:
        start = datetime(batch - 1, rng.choice([5, 6]), 1)
        end = start + timedelta(days=rng.choice([60, 90, 120]))
        co = rng.choice(FAKE_COMPANIES)
        used = rng.sample(skills, 2)
        exp_html = (f"<h2>Experience</h2><p><b>{INTERN_ROLES[branch]}</b>, {co} ({start:%b %Y} - {end:%b %Y})</p>"
                    f"<ul><li>Worked with {used[0]} and {used[1]} on a production feature.</li></ul>")
    body = f"""<h1>{name}</h1><p>{email} | +91 9{rng.randint(100000000, 999999999)}</p>
<h2>Summary</h2><p>Final-year {DEGREE[branch]} student interested in {skills[0]} and {skills[1]}.</p>
<h2>Technical Skills</h2><p>{', '.join(skills)}</p>
{exp_html}
<h2>Projects</h2><ul>{''.join(f'<li>{p}.</li>' for p in projects)}</ul>
<h2>Education</h2><p>B.E. in {DEGREE[branch]}, {INSTITUTION} ({batch - 4} - {batch}), CGPA {cgpa:.2f}</p>"""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_htmlbox(fitz.Rect(40, 40, 555, 802), f"<html><body>{body}</body></html>", css=CSS)
    data = doc.tobytes()
    doc.close()
    return data, skills


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def wipe(db) -> None:  # type: ignore[no-untyped-def]
    inst = db.scalars(select(Institution).where(Institution.code == INST_CODE)).first()
    users = db.scalars(select(User).where(User.email.like(f"%@{DOMAIN}") | User.email.like("%.demo@skillmatch.test")
                                          | User.email.in_([TPO_EMAIL, "tpo.demo@skillmatch.test"]))).all()
    cand_ids = list(db.scalars(select(Candidate.id).where(Candidate.user_id.in_([u.id for u in users]))))
    for cid in cand_ids:
        resume_store.delete(cid)
    if cand_ids:
        db.execute(delete(Candidate).where(Candidate.id.in_(cand_ids)))
    for u in users:
        db.delete(u)
    if inst is not None:
        db.delete(inst)
    db.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    configure_logging("WARNING")
    rng = random.Random(args.seed)
    t0 = time.perf_counter()
    with SessionLocal() as db:
        wipe(db)
        inst = Institution(name=INSTITUTION, code=INST_CODE, invite_code=INVITE)
        db.add(inst)
        db.flush()
        tpo = User(email=TPO_EMAIL, password_hash=hash_password(PASSWORD), full_name="Demo Placement Officer",
                   role="tpo", institution_id=inst.id)
        db.add(tpo)
        db.commit()

        branches = list(BRANCH_SKILLS)
        now = datetime.now(timezone.utc)
        logins: list[tuple[str, str, str]] = []
        used_names: set[str] = set()
        for i in range(args.students):
            branch = branches[i % len(branches)]
            gender = "female" if rng.random() < 0.42 else "male"
            while True:
                first = rng.choice(FEMALE if gender == "female" else MALE)
                name = f"{first} {rng.choice(LAST)}"
                if name not in used_names:
                    used_names.add(name)
                    break
            batch = 2027 if branch in ("ECE", "EEE") and (i // len(branches)) % 3 == 0 else 2026  # pre-final-year interns
            cgpa = round(clip(rng.gauss(7.4, 0.85), 5.2, 9.8), 2)
            active = rng.choice([1, 2]) if rng.random() < 0.08 else 0
            history = max(active, rng.choice([1, 2, 3]) if rng.random() < 0.15 else 0)
            tenth = round(clip(rng.gauss(85, 7), 60, 99), 1)
            diploma = round(clip(rng.gauss(75, 8), 55, 95), 1) if rng.random() < 0.1 else None
            twelfth = None if diploma else round(clip(rng.gauss(80, 9), 55, 98), 1)
            email = f"{first.lower()}.{i + 1:03d}@{DOMAIN}"
            roll = f"4WI{batch % 100 - 4:02d}{branch[:2]}{i + 1:03d}"
            u = User(email=email, password_hash=hash_password(PASSWORD), full_name=name, role="student", institution_id=inst.id)
            db.add(u)
            db.flush()
            r = rng.random()
            consent_at = None if r < 0.05 else now - timedelta(days=rng.randint(10, 60))
            withdrawn = now - timedelta(days=2) if 0.05 <= r < 0.085 else None
            p = StudentProfile(user_id=u.id, institution_id=inst.id, roll_no=roll, branch=branch, batch_year=batch,
                               cgpa=cgpa, active_backlogs=active, history_backlogs=history, tenth_pct=tenth,
                               twelfth_pct=twelfth, diploma_pct=diploma, gender=gender, consent_given_at=consent_at,
                               consent_withdrawn_at=withdrawn)
            if rng.random() < 0.12 and batch == 2026:
                p.placed_status = rng.choice(["offered", "placed"])
                p.current_best_offer_ctc = round(rng.uniform(4.0, 8.0), 1)
            db.add(p)
            pdf, _ = resume_pdf(rng, name, email, branch, cgpa, batch)
            res = process_pdf(pdf, bias_aware=True)
            cand = Candidate(user_id=u.id, filename=f"{roll}.pdf", raw_text=res.raw_text, masked_text=res.masked_text,
                             sections=res.sections, skills=res.skills, years_experience=res.years_experience,
                             education_level=res.education_level, education_rank=res.education_rank, bias_aware=True,
                             pages=res.pages)
            db.add(cand)
            db.flush()
            resume_store.save(cand.id, pdf)
            warm_profile(cand)
            db.commit()
            if i < 3 or branch == "MECH" and not any(b == "MECH" for _, _, b in logins):
                logins.append((name, email, branch))
            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/{args.students} students ({time.perf_counter() - t0:.0f}s)", flush=True)

        drive_ids: list[str] = []
        for spec in DRIVES:
            rules = spec.pop("rules")
            jd = spec.pop("jd")
            d = Drive(institution_id=inst.id, created_by=tpo.id, jd_text=jd, skills=extract_drive_skills(jd), status="open",
                      deadline=now + timedelta(days=rng.randint(5, 20)), **spec)
            db.add(d)
            db.flush()
            db.add(EligibilityRule(drive_id=d.id, **rules))
            drive_ids.append(d.id)
        db.commit()

        # A few student applications so dashboards are not empty (stages and offers grow in Phase 5C).
        students = db.scalars(select(StudentProfile).where(StudentProfile.institution_id == inst.id)).all()
        for d_id, branch_set in ((drive_ids[0], {"CSE", "IT"}), (drive_ids[2], {"CSE", "IT"})):
            for p in rng.sample([s for s in students if s.branch in branch_set and s.has_consent], 12):
                db.add(DriveApplication(drive_id=d_id, student_id=p.user_id, stage="Applied", source="student",
                                        stage_history=[{"stage": "Applied", "at": now.isoformat(), "by": "student"}]))
        db.commit()

    print(f"\nSeeded in {time.perf_counter() - t0:.0f}s: {args.students} students, {len(DRIVES)} drives.")
    print(f"\nDemo logins (password for all: {PASSWORD})")
    print(f"  Placement officer : {TPO_EMAIL}")
    for name, email, branch in logins[:4]:
        print(f"  Student ({branch:<4})    : {email}   ({name})")
    print(f"  Student invite code: {INVITE}")


if __name__ == "__main__":
    main()
