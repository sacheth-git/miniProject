"""Latency benchmark for /match on the real job index (CPU).

Parses each sample resume, warms up once, then times repeated match() calls,
with and without filters. Prints p50/p95 and the per-stage breakdown.

Usage (from backend/): .\\.venv\\Scripts\\python.exe scripts\\bench_match.py [--runs 10]
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import BACKEND_DIR, get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.embeddings.faiss_index import get_index  # noqa: E402
from app.matching.service import MatchFilters, match  # noqa: E402
from app.models.candidate import Candidate  # noqa: E402
from app.services.resume_pipeline import process_pdf  # noqa: E402

SAMPLES = BACKEND_DIR / "data" / "samples"


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    args = ap.parse_args()
    configure_logging("WARNING")
    index = get_index()
    if index is None:
        sys.exit("No index. Run scripts/build_index.py first.")
    print(f"index: {len(index)} jobs, model {index.model_name}, weights a/b/g/d = "
          f"{get_settings().w_alpha}/{get_settings().w_beta}/{get_settings().w_gamma}/{get_settings().w_delta}")
    scenarios = {"no filters": MatchFilters(), "india + full-time": MatchFilters(location="india", job_type="full-time")}
    with SessionLocal() as db:
        for pdf in sorted(SAMPLES.glob("*.pdf")):
            r = process_pdf(pdf.read_bytes())
            cand = Candidate(filename=pdf.name, raw_text=r.raw_text, masked_text=r.masked_text, sections=r.sections,
                             skills=r.skills, years_experience=r.years_experience, education_level=r.education_level,
                             education_rank=r.education_rank, bias_aware=True, pages=r.pages)
            db.add(cand)
            db.commit()
            for name, f in scenarios.items():
                match(db, cand, f, limit=20, persist=False)  # warm-up (model, caches)
                times: list[float] = []
                stages: dict[str, list[float]] = {}
                for _ in range(args.runs):
                    t0 = time.perf_counter()
                    run = match(db, cand, f, limit=20, persist=False)
                    times.append((time.perf_counter() - t0) * 1000)
                    for k, v in run.timings_ms.items():
                        stages.setdefault(k, []).append(v)
                top = run.items[0] if run.items else None
                print(f"{pdf.stem:<16} {name:<18} p50={statistics.median(times):6.0f} ms  p95={pct(times, 0.95):6.0f} ms  "
                      f"retrieved={run.retrieved:<4} stages(ms)={ {k: round(statistics.median(v)) for k, v in stages.items()} }  "
                      f"top: {top.job.title[:40] + ' @ ' + top.job.company[:18] if top else '-'} ({round(top.breakdown.score * 100) if top else 0}%)")
            db.delete(cand)
            db.commit()


if __name__ == "__main__":
    main()
