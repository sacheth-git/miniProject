r"""One-off: point existing Greenhouse jobs' Apply at the hosted application form.

New ingests do this in app/ingestion/sources/greenhouse.py; this updates rows ingested before.
Usage (repo root): backend\.venv\Scripts\python.exe backend\scripts\direct_apply_links.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.ingestion.sources.greenhouse import application_form_url  # noqa: E402
from app.models.job import Job  # noqa: E402


def main() -> None:
    changed = 0
    with SessionLocal() as db:
        for job in db.scalars(select(Job).where(Job.source == "greenhouse")):
            token, _, jid = (job.source_job_id or "").partition(":")
            if not jid:
                continue
            form = application_form_url(token, jid)
            if job.apply_url == form:
                continue
            opts = [o for o in (job.apply_options or []) if o.get("url") != form]
            board = (opts[0]["publisher"].removesuffix(" careers (Greenhouse)") if opts else job.company)
            job.apply_options = [{"publisher": f"{board} application form", "url": form, "is_direct": True}, *opts]
            job.apply_url = form
            changed += 1
        db.commit()
    print(f"Updated {changed} Greenhouse jobs to open the application form directly.")


if __name__ == "__main__":
    main()
