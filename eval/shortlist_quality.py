"""Campus evaluation (spec section J): shortlist quality, fairness, and the time-saved study.

1. Shortlist quality: for each demo drive, writes eval/data/shortlist_gold/<company>.csv with the eligible
   students (roll no., branch, CGPA, skills; no names) and an empty `label` column (0-3) for a TPO or
   faculty member to fill in blind. Once filled, re-run to get P@K, NDCG@K and Kendall tau of the
   system ranking against the human judgement.
2. Fairness: shortlist rates by gender and branch on the demo campus (system top-K vs actual).
3. Time-saved study: writes a timing sheet template and summarises it when filled in.

Usage (repo root): backend\\.venv\\Scripts\\python.exe eval\\shortlist_quality.py
"""

from __future__ import annotations

import csv
import re

from common import DATA, RESULTS, all_metrics, kendall_tau, ndcg_at, np, ranks_desc

GOLD_DIR = DATA / "shortlist_gold"
TIME_SHEET = DATA / "time_study.csv"
K = 10


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def main() -> None:
    from sqlalchemy import select

    from app.campus.analytics import fairness
    from app.campus.drives import in_drive, rank_drive
    from app.core.db import SessionLocal
    from app.core.logging import configure_logging
    from app.models.campus import Drive
    from app.models.user import Institution

    configure_logging("WARNING")
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    md = ["# Campus evaluation", ""]
    with SessionLocal() as db:
        inst = db.scalars(select(Institution).where(Institution.code == "WITDEMO")).first()
        if inst is None:
            raise SystemExit("Seed the demo campus first: backend\\.venv\\Scripts\\python.exe backend\\scripts\\seed_demo.py")
        drives = list(db.scalars(select(Drive).where(Drive.institution_id == inst.id, Drive.status != "draft")))

        md += ["## Shortlist quality against human judgement", "",
               "| Drive | Eligible ranked | Human-labelled | P@10 | NDCG@10 | Kendall tau |", "|---|---:|---:|---:|---:|---:|"]
        labelled_any = False
        for d in drives:
            recs = [r for r in rank_drive(db, d) if in_drive(r) and r.breakdown is not None]
            path = GOLD_DIR / f"{safe(d.company)}.csv"
            labels: dict[str, int] = {}
            if path.exists():
                for row in csv.DictReader(path.open(encoding="utf-8")):
                    if row.get("label", "").strip() != "":
                        labels[row["roll_no"]] = int(row["label"])
            else:
                # Blind template: no names, rows in random order so the system rank is not given away.
                rng = np.random.default_rng(0)
                with path.open("w", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh)
                    w.writerow(["roll_no", "branch", "cgpa", "skills_from_resume", "drive", "label"])
                    for i in rng.permutation(len(recs)):
                        r = recs[i]
                        w.writerow([r.profile.roll_no, r.profile.branch, r.profile.cgpa,
                                    "; ".join(s["name"] for s in (r.candidate.skills or [])[:15]) if r.candidate else "",
                                    f"{d.company}: {d.role}", ""])
            if len(labels) >= 5:
                labelled_any = True
                rows = [r for r in recs if r.profile.roll_no in labels]
                scores = np.array([r.breakdown.score for r in rows])  # type: ignore[union-attr]
                y = np.array([labels[r.profile.roll_no] for r in rows], dtype=float)  # type: ignore[index]
                m = all_metrics(scores, y)
                md.append(f"| {d.company}: {d.role} | {len(recs)} | {len(rows)} | {m['P@10']:.2f} | "
                          f"{ndcg_at(ranks_desc(scores), y, K):.2f} | {kendall_tau(scores, y):.2f} |")
            else:
                md.append(f"| {d.company}: {d.role} | {len(recs)} | 0 | pending | pending | pending |")
        if not labelled_any:
            md += ["", f"Pending: fill the `label` column (0-3) in `eval/data/shortlist_gold/*.csv` (blind: no names, "
                       "random order), then re-run this script."]

        fr = fairness(db, inst.id)
        md += ["", "## Fairness on the demo campus", "", fr["note"], "",
               f"Drives with a shortlist: {fr['drives_used']}.", ""]
        for dim in ("gender", "branch"):
            t = fr[dim]
            md += [f"**By {dim}** (parity, system {t['system_parity']}, actual {t['actual_parity']})", "",
                   "| Group | Eligible | System top-K rate | Actual shortlist rate |", "|---|---:|---:|---:|"]
            for r in t["rows"]:
                md.append(f"| {r['group']} | {r['eligible'] if not r['suppressed'] else 'hidden (<10)'} | "
                          f"{'' if r['suppressed'] else str(r['system_rate']) + '%'} | {'' if r['suppressed'] else str(r['actual_rate']) + '%'} |")
            md.append("")
        md += ["Blind mode hides names and email in the TPO's view. The score itself never sees name or gender, so the "
               "system's recommended set is identical with blind mode on or off; any difference between blind and named "
               "reviews comes from the human step, which the time-saved study below measures.", ""]

    if not TIME_SHEET.exists():
        with TIME_SHEET.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows([["volunteer", "condition", "blind", "drive", "resumes_reviewed", "minutes", "shortlisted_roll_nos"],
                                      ["tpo1", "manual", "no", "Kaveri Systems", "50", "", ""],
                                      ["tpo1", "skillmatch", "yes", "Deccan Motors", "50", "", ""]])
    sheet = [r for r in csv.DictReader(TIME_SHEET.open(encoding="utf-8")) if r["minutes"].strip()]
    md += ["## Time-saved study", ""]
    if sheet:
        by = {c: [float(r["minutes"]) for r in sheet if r["condition"] == c] for c in ("manual", "skillmatch")}
        if by["manual"] and by["skillmatch"]:
            man, sm = np.mean(by["manual"]), np.mean(by["skillmatch"])
            md.append(f"Manual: {man:.1f} min, with HireX: {sm:.1f} min for 50 resumes "
                      f"({100 * (man - sm) / man:.0f}% less time, {len(sheet)} sessions).")
    else:
        md += ["Pending. Protocol: 2-3 TPO or faculty volunteers each shortlist 10 from 50 resumes twice (different drives, "
               "order counterbalanced): once by hand from the PDFs, once with HireX's ranked, explained list. Record "
               "minutes and the chosen roll numbers in `eval/data/time_study.csv`; agreement between the two shortlists "
               "and with the system's top 10 is reported alongside the time saved."]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "campus_eval.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
