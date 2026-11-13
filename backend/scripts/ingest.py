"""Run job ingestion from the command line.

Usage (from backend/):
    .\\.venv\\Scripts\\python.exe scripts\\ingest.py                      # all sources
    .\\.venv\\Scripts\\python.exe scripts\\ingest.py greenhouse lever     # subset
    .\\.venv\\Scripts\\python.exe scripts\\ingest.py --check-links        # link checker only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.ingestion.http import HttpClient  # noqa: E402
from app.ingestion.link_checker import check_links  # noqa: E402
from app.ingestion.pipeline import run_ingestion  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="*", help="source names (default: all)")
    ap.add_argument("--check-links", action="store_true")
    ap.add_argument("--dedup-only", action="store_true", help="re-run dedup over stored jobs")
    ap.add_argument("--limit", type=int, default=500, help="max links to check")
    args = ap.parse_args()
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    t0 = time.perf_counter()
    with SessionLocal() as db:
        if args.dedup_only:
            from app.embeddings.encoder import get_encoder
            from app.ingestion.pipeline import run_dedup

            print(json.dumps(run_dedup(db, get_encoder()), indent=2))
        elif args.check_links:
            http = HttpClient(cache_dir=None)
            try:
                print(json.dumps(check_links(db, http, limit=args.limit), indent=2))
            finally:
                http.close()
        else:
            report = run_ingestion(db, args.sources or None)
            print(json.dumps(report.to_dict(), indent=2))
    print(f"done in {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
