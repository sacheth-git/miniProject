r"""Build the Hugging Face Space bundle in deploy/build/.

Copies the backend code, the built frontend, the job index and a cleaned copy of the database that keeps
only public job listings and the fictional demo campus (WITDEMO). Every other account, resume, private
import, notification and audit entry is removed, so no real person's data leaves this machine.

Usage (repo root, after `npm run build` in frontend/):
    backend\.venv\Scripts\python.exe backend\scripts\make_deploy_bundle.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
OUT = ROOT / "deploy" / "build"
DEMO_DOMAIN = "@demo.skillmatch.example"
DEMO_CODE = "WITDEMO"
# Evaluation-only packages the running app never imports.
SKIP_REQS = ("matplotlib", "datasets", "accelerate", "pytest", "pytest-cov")


def copytree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))


def clean_db(path: Path) -> dict[str, int]:
    c = sqlite3.connect(path)
    c.execute("PRAGMA foreign_keys = OFF")
    inst = c.execute("SELECT id FROM institutions WHERE code = ?", (DEMO_CODE,)).fetchone()
    if inst is None:
        raise SystemExit("Demo campus missing: run backend/scripts/seed_demo.py first")
    keep = inst[0]
    q = c.execute
    q("DELETE FROM users WHERE email NOT LIKE ? OR institution_id IS NOT ?", (f"%{DEMO_DOMAIN}", keep))
    q("DELETE FROM institutions WHERE id != ?", (keep,))
    for t in ("drives", "offers", "audit_log", "share_links", "student_profiles", "import_jobs"):
        q(f"DELETE FROM {t} WHERE institution_id IS NOT ?", (keep,))
    q("DELETE FROM eligibility_rules WHERE drive_id NOT IN (SELECT id FROM drives)")
    q("DELETE FROM drive_applications WHERE drive_id NOT IN (SELECT id FROM drives) OR student_id NOT IN (SELECT id FROM users)")
    q("DELETE FROM offers WHERE student_id NOT IN (SELECT id FROM users)")
    q("DELETE FROM student_profiles WHERE user_id NOT IN (SELECT id FROM users)")
    q("DELETE FROM notifications WHERE user_id NOT IN (SELECT id FROM users)")
    q("DELETE FROM audit_log WHERE actor_id IS NOT NULL AND actor_id NOT IN (SELECT id FROM users)")
    q("DELETE FROM share_links")  # links are bearer tokens; none should travel
    q("DELETE FROM candidates WHERE user_id IS NULL OR user_id NOT IN (SELECT id FROM users)")
    q("DELETE FROM applications WHERE candidate_id NOT IN (SELECT id FROM candidates)")
    q("DELETE FROM matches")
    q("DELETE FROM jobs WHERE owner_id IS NOT NULL")  # private imports
    c.commit()
    stats = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("users", "institutions", "candidates", "jobs")}
    leaked = c.execute("SELECT COUNT(*) FROM users WHERE email NOT LIKE ?", (f"%{DEMO_DOMAIN}",)).fetchone()[0]
    if leaked:
        raise SystemExit(f"Refusing to build: {leaked} non-demo accounts left in the database")
    c.execute("VACUUM")
    c.close()
    return stats


def main() -> None:
    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").exists():
        raise SystemExit("Build the frontend first: cd frontend && npm run build")
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "backend" / "data").mkdir(parents=True)

    for f in ("Dockerfile", "README.md"):
        shutil.copy2(ROOT / "deploy" / "huggingface" / f, OUT / f)
    copytree(BACKEND / "app", OUT / "backend" / "app")
    shutil.copy2(BACKEND / "serve.py", OUT / "backend" / "serve.py")
    copytree(dist, OUT / "frontend" / "dist")

    reqs = []
    for name in ("requirements.txt", "requirements-ml.txt"):
        for line in (BACKEND / name).read_text(encoding="utf-8").splitlines():
            pkg = line.split("==")[0].split(">=")[0].split("[")[0].strip().lower()
            if line.strip() and not line.lstrip().startswith("#") and pkg not in SKIP_REQS:
                reqs.append(line.split("#")[0].strip())
    (OUT / "backend" / "requirements-deploy.txt").write_text("\n".join(reqs) + "\n", encoding="utf-8")

    data = BACKEND / "data"
    for d in ("taxonomy", "faiss", "seeds"):
        copytree(data / d, OUT / "backend" / "data" / d)
    shutil.copy2(data / "learned_weights.json", OUT / "backend" / "data" / "learned_weights.json")
    (OUT / "backend" / "data" / "cache").mkdir()
    shutil.copy2(data / "cache" / "embeddings.sqlite", OUT / "backend" / "data" / "cache" / "embeddings.sqlite")

    db = OUT / "backend" / "skillmatch.db"
    shutil.copy2(BACKEND / "skillmatch.db", db)
    stats = clean_db(db)

    # Original PDFs only for the demo students that remain.
    keep = {r[0] for r in sqlite3.connect(db).execute("SELECT id FROM candidates")}
    (OUT / "backend" / "data" / "resumes").mkdir()
    copied = 0
    for pdf in (data / "resumes").glob("*.pdf"):
        if pdf.stem in keep:
            shutil.copy2(pdf, OUT / "backend" / "data" / "resumes" / pdf.name)
            copied += 1

    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1e6
    print(f"Bundle ready in {OUT} ({size:.0f} MB)")
    print(f"Database: {stats['jobs']:,} jobs, {stats['users']} demo accounts, {stats['candidates']} demo resumes, "
          f"{stats['institutions']} institution; {copied} demo resume PDFs")


if __name__ == "__main__":
    sys.exit(main())
