"""Latency benchmark (CPU): resume encoding, and /match query time at 1k / 10k / 50k jobs.

Query = build profile (cached embeddings) + FAISS top-300 over N jobs + full re-scoring of the
300 candidates. Above the real corpus size, the index is padded with the real job vectors
plus small noise (re-normalised), which keeps retrieval cost realistic.

Usage (repo root): backend\\.venv\\Scripts\\python.exe eval\\latency.py
"""

from __future__ import annotations

import statistics
import time

from common import BACKEND, RESULTS, load_json, np, DATA, candidate_from_parsed

SIZES = (1_000, 10_000, 50_000)
RUNS = 20


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main() -> None:
    import faiss
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.core.logging import configure_logging
    from app.embeddings.encoder import get_encoder
    from app.embeddings.faiss_index import get_index
    from app.matching.service import build_profile, get_scorer, get_skill_space, job_features
    from app.models.job import Job
    from app.services.resume_pipeline import process_pdf

    configure_logging("WARNING")
    enc, index, scorer, space = get_encoder(), get_index(), get_scorer(), get_skill_space()
    assert index is not None
    parsed = [p for p in load_json(DATA / "parsed.json") if p["bias_aware"]]
    pdfs = sorted((DATA / "resumes").glob("*.pdf"))[:10]

    # Warm-up (model load, taxonomy vectors)
    process_pdf(pdfs[0].read_bytes())
    build_profile(candidate_from_parsed(parsed[0]), enc, space)

    parse_ms, cold_encode_ms = [], []
    for p in pdfs:
        t = time.perf_counter()
        r = process_pdf(p.read_bytes())
        parse_ms.append((time.perf_counter() - t) * 1000)
        texts = [f"latency-probe-{time.time_ns()} " + (r.masked_text or "")]  # unseen text: no cache hit
        t = time.perf_counter()
        enc.encode(texts)
        cold_encode_ms.append((time.perf_counter() - t) * 1000)

    base = index.doc.astype(np.float32)
    rng = np.random.default_rng(0)
    with SessionLocal() as db:
        jobs = list(db.scalars(select(Job).where(Job.id.in_(index.ids[:300]))))
    feats = job_features(jobs, index, enc)
    rows = []
    for n in SIZES:
        if n <= len(base):
            mat = base[:n]
        else:
            reps = int(np.ceil(n / len(base)))
            mat = np.concatenate([base + rng.normal(0, 0.01, base.shape).astype(np.float32) for _ in range(reps)])[:n]
            mat /= np.linalg.norm(mat, axis=1, keepdims=True)
        fx = faiss.IndexFlatIP(mat.shape[1])
        fx.add(np.ascontiguousarray(mat))
        totals, searches, scores = [], [], []
        for k in range(RUNS):
            cand = candidate_from_parsed(parsed[k % len(parsed)])
            t0 = time.perf_counter()
            prof = build_profile(cand, enc, space)
            t1 = time.perf_counter()
            fx.search(prof.full_vec.reshape(1, -1).astype(np.float32), 300)
            t2 = time.perf_counter()
            for f in feats:
                scorer.score(prof, f, index.idf)
            t3 = time.perf_counter()
            totals.append((t3 - t0) * 1000)
            searches.append((t2 - t1) * 1000)
            scores.append((t3 - t2) * 1000)
        rows.append((n, statistics.median(totals), pct(totals, 0.95), statistics.median(searches), statistics.median(scores)))
        print(f"N={n:>6}: p50 {rows[-1][1]:.0f} ms, p95 {rows[-1][2]:.0f} ms (search {rows[-1][3]:.1f} ms, re-score 300 {rows[-1][4]:.0f} ms)")

    md = [
        "# Latency (CPU, warm)",
        "",
        f"Resume parse + skill extraction (embedding cache warm for these resumes; a first-time resume adds about one encoding per section): median {statistics.median(parse_ms):.0f} ms (p95 {pct(parse_ms, 0.95):.0f} ms) over {len(pdfs)} resumes.",
        f"Encoding one unseen resume text (bge-small, 512 tokens): median {statistics.median(cold_encode_ms):.0f} ms.",
        "",
        "| Jobs indexed | Query p50 (ms) | Query p95 (ms) | FAISS search (ms) | Re-score top 300 (ms) |",
        "|---:|---:|---:|---:|---:|",
        *[f"| {n:,} | {a:.0f} | {b:.0f} | {c:.1f} | {d:.0f} |" for n, a, b, c, d in rows],
        "",
        f"Query = profile from cached embeddings + exact inner-product search (IndexFlatIP) + full re-scoring; {RUNS} runs each.",
        "The live API adds the database load of the 300 candidates (about 20 ms; see backend/scripts/bench_match.py).",
    ]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "latency.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 3.2), dpi=150)
    ns = [r[0] for r in rows]
    ax.plot(ns, [r[1] for r in rows], marker="o", color="#2a78d6", linewidth=2, label="p50")
    ax.plot(ns, [r[2] for r in rows], marker="o", color="#2a78d6", linewidth=1, linestyle="--", label="p95")
    for n, a in zip(ns, [r[1] for r in rows]):
        ax.annotate(f"{a:.0f} ms", (n, a), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)
    ax.set_xscale("log")
    ax.set_xticks(ns, [f"{n // 1000}k" for n in ns])
    ax.set_xlabel("Jobs indexed", fontsize=9)
    ax.set_ylabel("Query time (ms)", fontsize=9)
    ax.set_title("Match latency on CPU", fontsize=10, loc="left")
    ax.grid(color="#e4e3df", linewidth=0.8)
    ax.legend(frameon=False, fontsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(RESULTS / "latency.png")
    print((RESULTS / "latency.md").read_text(encoding="utf-8"))
    _ = BACKEND


if __name__ == "__main__":
    main()
