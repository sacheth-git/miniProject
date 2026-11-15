"""Shortlist exports: Excel, CSV, PDF summary, ZIP of resumes."""

from __future__ import annotations

import csv
import html
import io
import re
import zipfile
from collections.abc import Sequence
from typing import Any

import fitz
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from app.models.campus import Drive
from app.services import resume_store

COLUMNS: dict[str, str] = {
    "rank": "Rank",
    "roll_no": "Roll no.",
    "name": "Name",
    "email": "Email",
    "branch": "Branch",
    "batch_year": "Batch",
    "cgpa": "CGPA",
    "match_percent": "Match %",
    "matched_skills": "Top matched skills",
    "missing_required": "Missing required skills",
    "placed_status": "Placed status",
    "stage": "Stage",
}
BLIND_HIDDEN = {"name", "email"}
DEFAULT_COLUMNS = ["rank", "roll_no", "name", "branch", "cgpa", "match_percent", "matched_skills", "missing_required"]


def pick_columns(requested: Sequence[str] | None, blind: bool) -> list[str]:
    cols = [c for c in (requested or DEFAULT_COLUMNS) if c in COLUMNS]
    if blind:
        cols = [c for c in cols if c not in BLIND_HIDDEN]
    return cols or ["rank", "roll_no"]


def _cell(row: dict[str, Any], col: str) -> Any:
    v = row.get(col)
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return "" if v is None else v


def safe_filename(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")[:60] or "shortlist"


def to_csv(rows: list[dict[str, Any]], cols: list[str]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([COLUMNS[c] for c in cols])
    for r in rows:
        w.writerow([_cell(r, c) for c in cols])
    return buf.getvalue().encode("utf-8-sig")  # BOM: Excel opens UTF-8 correctly


def to_xlsx(rows: list[dict[str, Any]], cols: list[str], drive: Drive) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Shortlist"
    ws.append([f"{drive.company}: {drive.role}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([f"{len(rows)} students · CTC {drive.ctc_lpa or '-'} LPA · {drive.location or ''}"])
    ws.append([])
    ws.append([COLUMNS[c] for c in cols])
    header_row = ws.max_row
    for i in range(1, len(cols) + 1):
        c = ws.cell(row=header_row, column=i)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1D4ED8")
    for r in rows:
        ws.append([_cell(r, c) for c in cols])
    for i, col in enumerate(cols, 1):
        width = max(len(COLUMNS[col]), *(len(str(_cell(r, col))) for r in rows)) if rows else len(COLUMNS[col])
        ws.column_dimensions[get_column_letter(i)].width = min(60, width + 2)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_pdf(rows: list[dict[str, Any]], cols: list[str], drive: Drive, note: str) -> bytes:
    e = html.escape
    head = "".join(f"<th>{e(COLUMNS[c])}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{e(str(_cell(r, c)))}</td>" for c in cols) + "</tr>" for r in rows)
    doc_html = f"""
    <h1>{e(drive.company)}: {e(drive.role)}</h1>
    <p class="meta">Type: {e(drive.job_type)} · CTC: {e(str(drive.ctc_lpa or '-'))} LPA · Location: {e(drive.location or '-')}
    · Category: {e(drive.category)} · Rounds: {e(', '.join(drive.rounds or []) or '-')}</p>
    <p class="meta">{len(rows)} students shortlisted. {e(note)}</p>
    <table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"""
    css = """* { font-family: sans-serif; font-size: 8.5pt; }
    h1 { font-size: 14pt; margin: 0 0 4pt 0; } .meta { color: #444; margin: 0 0 4pt 0; }
    table { border-collapse: collapse; width: 100%; } th { background: #1d4ed8; color: #fff; text-align: left; }
    th, td { border: 1px solid #bbb; padding: 2pt 3pt; vertical-align: top; }"""
    story = fitz.Story(html=doc_html, user_css=css)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    rect = fitz.paper_rect("a4-l")
    where = rect + (30, 30, -30, -30)
    more = True
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()


def to_resume_zip(rows: list[dict[str, Any]], blind: bool) -> tuple[bytes, int]:
    """ZIP of shortlisted resumes named by roll number (names left out in blind mode)."""
    buf = io.BytesIO()
    n = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in rows:
            cid = r.get("candidate_id")
            data = resume_store.load(cid) if cid else None
            if data is None:
                continue
            label = r.get("roll_no") or f"rank{r.get('rank')}"
            if not blind and r.get("name"):
                label = f"{label}_{r['name']}"
            zf.writestr(f"{r.get('rank', 0):03d}_{safe_filename(str(label))}.pdf", data)
            n += 1
    return buf.getvalue(), n
