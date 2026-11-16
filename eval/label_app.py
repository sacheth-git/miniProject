"""Command-line relevance labeller for eval/data/gold/to_label.csv (resumable).

Usage (repo root): backend\\.venv\\Scripts\\python.exe eval\\label_app.py --annotator asha
Writes eval/data/gold/labels_<annotator>.csv. Keys: 0-3 to label, s to skip, b to go back, q to quit.

Scale
  3  Strong fit: this is the role the candidate is aiming for, at a level they could get
  2  Good fit: a closely related role they could reasonably apply to
  1  Weak fit: related field, but the wrong specialisation or seniority
  0  Not relevant
"""

from __future__ import annotations

import argparse
import csv
import textwrap

from common import GOLD, load_json, DATA


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotator", required=True)
    ap.add_argument("--limit", type=int, default=0, help="stop after this many new labels")
    args = ap.parse_args()
    src = GOLD / "to_label.csv"
    out = GOLD / f"labels_{args.annotator}.csv"
    rows = list(csv.DictReader(src.open(encoding="utf-8")))
    done: dict[tuple[str, str], str] = {}
    if out.exists():
        for r in csv.DictReader(out.open(encoding="utf-8")):
            done[(r["resume_id"], r["job_id"])] = r["label"]
    resumes = {p["id"]: p for p in load_json(DATA / "parsed.json") if p["bias_aware"]}
    todo = [r for r in rows if (r["resume_id"], r["job_id"]) not in done]
    print(__doc__.split("Scale")[1])
    print(f"{len(done)} labelled, {len(todo)} to go. Labels save after every answer.\n")
    history: list[tuple[str, str]] = []
    i, new = 0, 0
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if out.stat().st_size == 0:
            w.writerow(["resume_id", "job_id", "label", "annotator"])
        while i < len(todo):
            r = todo[i]
            res = resumes[r["resume_id"]]
            print("=" * 78)
            print(f"[{len(done) + 1}] Candidate {r['resume_id']} - aiming for: {r['target_role']}")
            print(f"    Skills: {', '.join(s['name'] for s in res['skills'][:14])}")
            print(f"    Experience: {res['years_experience']} years")
            print(f"Job: {r['job_title']} @ {r['company']}")
            print(textwrap.fill(r["snippet"], 78, initial_indent="    ", subsequent_indent="    "))
            ans = input("Label 0-3 (s skip, b back, q quit): ").strip().lower()
            if ans == "q":
                break
            if ans == "s":
                i += 1
                continue
            if ans == "b" and history:
                print("Going back is not supported once saved; re-label later by editing the CSV.")
                continue
            if ans not in {"0", "1", "2", "3"}:
                print("Please type 0, 1, 2 or 3.")
                continue
            w.writerow([r["resume_id"], r["job_id"], ans, args.annotator])
            f.flush()
            done[(r["resume_id"], r["job_id"])] = ans
            history.append((r["resume_id"], r["job_id"]))
            i += 1
            new += 1
            if args.limit and new >= args.limit:
                break
    print(f"Saved {new} new labels to {out}")


if __name__ == "__main__":
    main()
