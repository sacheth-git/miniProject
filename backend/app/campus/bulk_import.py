"""Bulk student onboarding: CSV (+ ZIP of {roll_no}.pdf resumes) -> preview -> commit.

Preview validates every row and reports errors and warnings without changing data.
Commit runs in a background thread, creating or updating student accounts
(temporary password + forced reset) and parsing each resume, with progress saved
to the ImportJob row.
"""

from __future__ import annotations

import csv
import io
import secrets
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select

from app.auth.security import hash_password
from app.core.config import BACKEND_DIR
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models.campus import ImportJob
from app.models.candidate import Candidate
from app.models.user import StudentProfile, User
from app.parsing.pdf_parser import PDFParseError
from app.services import resume_store
from app.services.audit import audit
from app.services.resume_pipeline import process_pdf


def warm_profile(cand: Candidate) -> None:
    """Embed the resume now so the first shortlist that includes this student is fast."""
    try:
        from app.matching.service import build_profile

        build_profile(cand)
    except Exception:  # warming is an optimisation; never fail the import over it
        log.warning("Could not pre-compute embeddings for %s", cand.id, exc_info=True)

log = get_logger(__name__)
IMPORT_DIR = BACKEND_DIR / "data" / "imports"
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_ZIP_BYTES = 200 * 1024 * 1024
MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000
BRANCHES = {"CSE", "IT", "ECE", "EEE", "MECH", "CIVIL", "AIML", "DS", "ISE", "CHEM", "BIOTECH"}

ALIASES = {
    "roll": "roll_no", "roll_number": "roll_no", "usn": "roll_no", "rollno": "roll_no",
    "full_name": "name", "student_name": "name",
    "batch_year": "batch", "year": "batch",
    "backlogs": "active_backlogs", "active": "active_backlogs",
    "history": "history_backlogs", "backlog_history": "history_backlogs",
    "10th": "tenth", "tenth_pct": "tenth", "ssc": "tenth",
    "12th": "twelfth", "twelfth_pct": "twelfth", "hsc": "twelfth", "puc": "twelfth",
    "diploma_pct": "diploma",
}
REQUIRED = ("roll_no", "name", "email", "branch", "batch", "cgpa")


class BulkImportError(ValueError):
    """Whole-file problem (bad CSV, bad ZIP)."""


def _norm_header(h: str) -> str:
    k = h.strip().lower().replace(" ", "_").replace("-", "_").replace("%", "").strip("_")
    return ALIASES.get(k, k)


def _num(v: str, kind: type, lo: float, hi: float, label: str, errors: list[str]) -> Any:
    v = (v or "").strip()
    if not v:
        return None
    try:
        x = kind(float(v)) if kind is int else float(v)
    except ValueError:
        errors.append(f"{label} '{v}' is not a number")
        return None
    if not (lo <= x <= hi):
        errors.append(f"{label} {v} is outside {lo:g}-{hi:g}")
        return None
    return x


def _zip_index(zip_bytes: bytes | None) -> dict[str, zipfile.ZipInfo]:
    if not zip_bytes:
        return {}
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise BulkImportError("The resumes file is not a valid ZIP") from exc
    index: dict[str, zipfile.ZipInfo] = {}
    for info in zf.infolist():
        name = Path(info.filename).name  # ignore folders; never extract paths
        if info.is_dir() or not name.lower().endswith(".pdf"):
            continue
        index[name[:-4].strip().upper()] = info
    return index


def parse_preview(csv_bytes: bytes, zip_bytes: bytes | None, db: Any, institution_id: str) -> list[dict[str, Any]]:
    if len(csv_bytes) > MAX_CSV_BYTES:
        raise BulkImportError("CSV larger than 2 MB")
    if zip_bytes and len(zip_bytes) > MAX_ZIP_BYTES:
        raise BulkImportError("ZIP larger than 200 MB")
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = csv_bytes.decode("latin-1")
    reader = csv.reader(io.StringIO(text))
    try:
        header = [_norm_header(h) for h in next(reader)]
    except StopIteration as exc:
        raise BulkImportError("CSV is empty") from exc
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise BulkImportError(f"CSV is missing column(s): {', '.join(missing)}")
    zindex = _zip_index(zip_bytes)

    existing_rolls = {
        (r or "").upper(): uid
        for r, uid in db.execute(
            select(StudentProfile.roll_no, StudentProfile.user_id).where(StudentProfile.institution_id == institution_id)
        ).all()
    }
    seen_roll: dict[str, int] = {}
    seen_email: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(reader, start=2):
        if not any(c.strip() for c in raw):
            continue
        if len(rows) >= MAX_ROWS:
            raise BulkImportError(f"More than {MAX_ROWS} rows; split the file")
        rec = {header[i]: (raw[i] if i < len(raw) else "") for i in range(len(header))}
        errors: list[str] = []
        warnings: list[str] = []
        roll = rec.get("roll_no", "").strip().upper()
        name = rec.get("name", "").strip()
        email = rec.get("email", "").strip().lower()
        branch = rec.get("branch", "").strip().upper()
        if not roll:
            errors.append("Roll number missing")
        if not name:
            errors.append("Name missing")
        try:
            email = validate_email(email, check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            errors.append(f"Email '{email}' is not valid" if email else "Email missing")
        if not branch:
            errors.append("Branch missing")
        elif branch not in BRANCHES:
            warnings.append(f"Unusual branch '{branch}'")
        batch = _num(rec.get("batch", ""), int, 2000, 2100, "Batch", errors)
        cgpa = _num(rec.get("cgpa", ""), float, 0, 10, "CGPA", errors)
        if cgpa is None and not any(e.startswith("CGPA") for e in errors):
            errors.append("CGPA missing")
        active = _num(rec.get("active_backlogs", "0") or "0", int, 0, 99, "Active backlogs", errors) or 0
        history = _num(rec.get("history_backlogs", "") or str(active), int, 0, 99, "Backlog history", errors) or 0
        tenth = _num(rec.get("tenth", ""), float, 0, 100, "10th %", errors)
        twelfth = _num(rec.get("twelfth", ""), float, 0, 100, "12th %", errors)
        diploma = _num(rec.get("diploma", ""), float, 0, 100, "Diploma %", errors)
        if twelfth is None and diploma is None:
            warnings.append("No 12th or diploma %")
        if roll:
            if roll in seen_roll:
                errors.append(f"Duplicate roll number (also on line {seen_roll[roll]})")
            seen_roll.setdefault(roll, line_no)
        if email:
            if email in seen_email:
                errors.append(f"Duplicate email (also on line {seen_email[email]})")
            seen_email.setdefault(email, line_no)
            other = db.scalars(select(User).where(func.lower(User.email) == email)).first()
            if other is not None and (other.institution_id not in (None, institution_id) or other.role == "tpo"):
                errors.append("Email belongs to an account outside this institution")
        info = zindex.get(roll)
        has_resume = info is not None
        if not has_resume:
            warnings.append(f"No resume {roll or '?'}.pdf in the ZIP")
        elif info.file_size > MAX_PDF_BYTES:  # type: ignore[union-attr]
            errors.append("Resume PDF larger than 5 MB")
        rows.append({
            "line": line_no, "roll_no": roll, "name": name, "email": email, "branch": branch, "batch": batch,
            "cgpa": cgpa, "active_backlogs": active, "history_backlogs": history, "tenth": tenth, "twelfth": twelfth,
            "diploma": diploma, "gender": (rec.get("gender") or "").strip().lower() or None,
            "has_resume": has_resume, "action": "update" if roll in existing_rolls else "create",
            "status": "error" if errors else ("warning" if warnings else "ok"), "errors": errors, "warnings": warnings,
        })
    if not rows:
        raise BulkImportError("CSV has a header but no student rows")
    return rows


def store_upload(job_id: str, csv_bytes: bytes, zip_bytes: bytes | None) -> None:
    d = IMPORT_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "students.csv").write_bytes(csv_bytes)
    if zip_bytes:
        (d / "resumes.zip").write_bytes(zip_bytes)


def _commit_worker(job_id: str, actor_id: str) -> None:
    d = IMPORT_DIR / job_id
    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        actor = db.get(User, actor_id)
        if job is None or actor is None:
            return
        zpath = d / "resumes.zip"
        zf = zipfile.ZipFile(zpath) if zpath.exists() else None
        zindex = _zip_index(zpath.read_bytes()) if zf else {}
        creds: list[dict[str, str]] = []
        try:
            for row in job.rows:
                if row["status"] == "error":
                    job.done += 1
                    db.commit()
                    continue
                try:
                    _commit_row(db, job, row, zf, zindex, creds)
                    db.commit()
                except Exception as exc:  # one bad row must not stop the import
                    db.rollback()
                    job = db.get(ImportJob, job_id)
                    assert job is not None
                    job.errors = [*job.errors, {"line": row["line"], "roll_no": row["roll_no"], "error": f"{type(exc).__name__}: {exc}"}]
                    log.exception("Import row %s failed", row["line"])
                job.done += 1
                db.commit()
            job.status = "done"
            job.credentials = creds
            job.finished_at = datetime.now(timezone.utc)
            audit(db, actor, "students.import", "import_job", job.id,
                  after={"created": job.created, "updated": job.updated, "resumes": job.resumes_parsed, "errors": len(job.errors)})
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(ImportJob, job_id)
            if job is not None:
                job.status, job.message = "failed", f"{type(exc).__name__}: {exc}"
                db.commit()
            log.exception("Import job %s failed", job_id)
        finally:
            if zf:
                zf.close()
            shutil.rmtree(d, ignore_errors=True)  # uploaded files are not kept


def _commit_row(db: Any, job: ImportJob, row: dict[str, Any], zf: zipfile.ZipFile | None,
                zindex: dict[str, zipfile.ZipInfo], creds: list[dict[str, str]]) -> None:
    user = db.scalars(select(User).where(func.lower(User.email) == row["email"])).first()
    if user is None:
        temp = secrets.token_urlsafe(9)
        user = User(email=row["email"], password_hash=hash_password(temp), full_name=row["name"], role="student",
                    institution_id=job.institution_id, must_reset_password=True)
        db.add(user)
        db.flush()
        creds.append({"roll_no": row["roll_no"], "name": row["name"], "email": row["email"], "temporary_password": temp})
        job.created += 1
    else:
        user.full_name = user.full_name or row["name"]
        user.role, user.institution_id = "student", job.institution_id
        job.updated += 1
    prof = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    if prof is None:
        prof = StudentProfile(user_id=user.id, institution_id=job.institution_id)  # consent pending until they sign in
        db.add(prof)
    prof.roll_no, prof.branch, prof.batch_year, prof.cgpa = row["roll_no"], row["branch"], row["batch"], row["cgpa"]
    prof.active_backlogs, prof.history_backlogs = row["active_backlogs"], row["history_backlogs"]
    prof.tenth_pct, prof.twelfth_pct, prof.diploma_pct = row["tenth"], row["twelfth"], row["diploma"]
    if row.get("gender"):
        prof.gender = row["gender"]
    info = zindex.get(row["roll_no"])
    if zf is not None and info is not None and info.file_size <= MAX_PDF_BYTES:
        data = zf.read(info)
        try:
            result = process_pdf(data, bias_aware=True)
        except PDFParseError as exc:
            job.errors = [*job.errors, {"line": row["line"], "roll_no": row["roll_no"], "error": f"Resume: {exc}"}]
            return
        cand = Candidate(
            user_id=user.id, filename=info.filename[:255], raw_text=result.raw_text, masked_text=result.masked_text,
            sections=result.sections, skills=result.skills, years_experience=result.years_experience,
            education_level=result.education_level, education_rank=result.education_rank, bias_aware=True,
            pages=result.pages,
        )
        db.add(cand)
        db.flush()
        resume_store.save(cand.id, data)
        warm_profile(cand)
        job.resumes_parsed += 1


# Tests run imports inline: their in-memory SQLite is one connection shared across threads.
RUN_INLINE = False


def start_commit(job_id: str, actor_id: str) -> threading.Thread | None:
    if RUN_INLINE:
        _commit_worker(job_id, actor_id)
        return None
    t = threading.Thread(target=_commit_worker, args=(job_id, actor_id), daemon=True, name=f"import-{job_id[:8]}")
    t.start()
    return t
