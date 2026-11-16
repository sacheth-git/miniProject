"""Build the gold set: 40 synthetic resumes x a 200-job pool, cached features, proxy labels,
and a pooled CSV for human labelling.

Usage (repo root): backend\\.venv\\Scripts\\python.exe eval\\build_gold.py [--seed 13]
Outputs in eval/data/: resumes/*.pdf, parsed.json, pool.json, features.npz,
gold/proxy_labels.csv, gold/to_label.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import time
from collections import defaultdict

from common import (
    DATA, FAMILIES, GOLD, ROLE_SPECS, SKILL_CONFIGS, candidate_from_parsed, job_family, make_resume_pdf, np,
    proxy_label, ranks_desc, save_json,
)

PER_FAMILY = 14
GENERIC = 20
POOL_SIZE = 200
PER_RESUME_FAMILY = 4


def parse_resumes(rng: random.Random) -> list[dict]:  # type: ignore[type-arg]
    from app.services.resume_pipeline import process_pdf

    out = []
    families = list(ROLE_SPECS)
    for i in range(len(families) * PER_RESUME_FAMILY):
        fam = families[i % len(families)]
        g = make_resume_pdf(rng, f"r{i + 1:02d}", fam)
        data = g.pdf.read_bytes()
        for bias in (True, False):
            r = process_pdf(data, bias_aware=bias)
            out.append({"id": g.id if bias else f"{g.id}-raw", "resume_id": g.id, "family": fam, "bias_aware": bias,
                        "name": g.name, "true_skills": g.skills, "raw_text": r.raw_text, "masked_text": r.masked_text,
                        "sections": r.sections, "skills": r.skills, "years_experience": r.years_experience,
                        "education_level": r.education_level, "education_rank": r.education_rank})
    return out


def select_pool(rng: random.Random) -> list[dict]:  # type: ignore[type-arg]
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.embeddings.faiss_index import get_index
    from app.models.job import Job

    index = get_index()
    assert index is not None, "Build the job index first (backend/scripts/build_index.py)"
    with SessionLocal() as db:
        rows = db.execute(select(Job.id, Job.title, Job.company).where(Job.id.in_(index.ids))).all()
    by_fam: dict[str | None, list] = defaultdict(list)  # type: ignore[type-arg]
    for r in rows:
        by_fam[job_family(r.title)].append(r)
    pool = []
    for fam in FAMILIES:
        cands = by_fam.get(fam, [])
        rng.shuffle(cands)
        take = GENERIC if fam == "swe" else PER_FAMILY
        # Prefer a mix: about half entry/mid titles, half senior ones (when the corpus has them).
        from common import SENIOR

        junior = [c for c in cands if not SENIOR.search(c.title)]
        senior = [c for c in cands if SENIOR.search(c.title)]
        pick = junior[: take // 2 + take % 2] + senior[: take // 2]
        pick += [c for c in cands if c not in pick][: take - len(pick)]
        pool += pick
    others = by_fam.get(None, [])
    rng.shuffle(others)
    pool += others[: POOL_SIZE - len(pool)]
    return [{"id": r.id, "title": r.title, "company": r.company, "family": job_family(r.title)} for r in pool[:POOL_SIZE]]


def compute_features(parsed: list[dict], pool: list[dict], encoder=None, use_index_vectors: bool = True) -> dict[str, np.ndarray]:  # type: ignore[type-arg, no-untyped-def]
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.embeddings.documents import job_document
    from app.embeddings.encoder import get_encoder
    from app.embeddings.faiss_index import get_index
    from app.matching import baselines
    from app.matching.calibration import calibration_for
    from app.matching.scorer import Scorer, ScorerConfig, Weights
    from app.matching.service import build_profile, candidate_texts, get_skill_space, job_features
    from app.models.job import Job

    enc = encoder or get_encoder()
    index = get_index()
    from app.matching.scorer import SkillSpace
    from app.skills.taxonomy import get_taxonomy

    space = get_skill_space() if encoder is None else SkillSpace(get_taxonomy(), enc)
    cal = calibration_for(enc.model_name)
    w = Weights(0.4, 0.4, 0.2, 0.15)
    with SessionLocal() as db:
        jobs_by_id = {j.id: j for j in db.scalars(select(Job).where(Job.id.in_([p["id"] for p in pool])))}
        jobs = [jobs_by_id[p["id"]] for p in pool]
        feats = job_features(jobs, index if use_index_vectors else None, enc)
        texts = [job_document(j.title, j.description) for j in jobs]
        job_skill_sets = [{s["skill_id"] for s in (j.required_skills or []) + (j.preferred_skills or [])} for j in jobs]
    n_r, n_j = len(parsed), len(pool)
    out: dict[str, np.ndarray] = {k: np.zeros((n_r, n_j), np.float32) for k in (
        "sem", "sem_full", "sem_raw", "sem_full_raw", "context", "tfidf", "bm25", "jaccard")}
    for name in SKILL_CONFIGS:
        out[f"skill_{name}"] = np.zeros((n_r, n_j), np.float32)
        out[f"pen_{name}"] = np.zeros((n_r, n_j), np.float32)
    scorers = {name: Scorer(space, cal, w, ScorerConfig(**cfg)) for name, cfg in SKILL_CONFIGS.items()}
    idf = index.idf
    for i, rec in enumerate(parsed):
        cand = candidate_from_parsed(rec)
        prof = build_profile(cand, enc, space)
        for j, f in enumerate(feats):
            base = scorers["full"].score(prof, f, idf)
            out["sem"][i, j], out["sem_full"][i, j], out["context"][i, j] = base.sem, base.sem_full, base.context
            nocal = scorers["no_cal"].score(prof, f, idf)
            out["sem_raw"][i, j], out["sem_full_raw"][i, j] = nocal.sem, float(prof.full_vec @ f.doc_vec)
            for name, sc in scorers.items():
                b = base if name == "full" else nocal if name == "no_cal" else sc.score(prof, f, idf)
                out[f"skill_{name}"][i, j], out[f"pen_{name}"][i, j] = b.skill, b.penalty
        full_text, _ = candidate_texts(cand)
        out["tfidf"][i] = baselines.tfidf_scores(full_text, texts)
        out["bm25"][i] = baselines.bm25_scores(full_text, texts)
        out["jaccard"][i] = baselines.keyword_jaccard({s["skill_id"] for s in cand.skills or []}, job_skill_sets)
        if (i + 1) % 10 == 0:
            print(f"  features for {i + 1}/{n_r} resume versions", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    from app.core.logging import configure_logging

    configure_logging("WARNING")
    rng = random.Random(args.seed)
    t0 = time.perf_counter()
    parsed = parse_resumes(rng)
    save_json(DATA / "parsed.json", parsed)
    print(f"parsed {len(parsed)} resume versions ({time.perf_counter() - t0:.0f}s)")
    pool = select_pool(rng)
    save_json(DATA / "pool.json", pool)
    fams = defaultdict(int)
    for p in pool:
        fams[p["family"]] += 1
    print(f"pool {len(pool)} jobs: {dict(fams)}")
    feats = compute_features(parsed, pool)
    np.savez_compressed(DATA / "features.npz", **feats, resume_ids=np.array([p["id"] for p in parsed]),
                        job_ids=np.array([p["id"] for p in pool]))
    print(f"features cached ({time.perf_counter() - t0:.0f}s)")

    # Proxy labels for every (resume, job) pair - title-based, independent of all methods.
    masked = [p for p in parsed if p["bias_aware"]]
    GOLD.mkdir(parents=True, exist_ok=True)
    with (GOLD / "proxy_labels.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["resume_id", "job_id", "label"])
        for r in masked:
            for p in pool:
                wr.writerow([r["id"], p["id"], proxy_label(r["family"], p["title"])])

    # Pooled pairs for human labelling: top-10 of every method + 5 random per resume.
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.job import Job

    w = (0.4, 0.4, 0.2, 0.15)
    idx = [i for i, p in enumerate(parsed) if p["bias_aware"]]
    ours = (w[0] * feats["sem"] + w[1] * feats["skill_full"] + w[2] * feats["context"] - w[3] * feats["pen_full"])
    methods = {"ours": ours, "tfidf": feats["tfidf"], "bm25": feats["bm25"], "jaccard": feats["jaccard"],
               "sbert_whole": feats["sem_full_raw"], "sbert_section": feats["sem"]}
    with SessionLocal() as db:
        desc = {j.id: j.description for j in db.scalars(select(Job).where(Job.id.in_([p["id"] for p in pool])))}
    rows = []
    for i in idx:
        chosen: set[int] = set()
        for m in methods.values():
            chosen.update(ranks_desc(m[i])[:10].tolist())
        chosen.update(rng.sample(range(len(pool)), 5))
        for j in sorted(chosen):
            snippet = " ".join(desc[pool[j]["id"]].split())[:400]
            rows.append([parsed[i]["id"], parsed[i]["family"], ROLE_SPECS[parsed[i]["family"]]["title"],
                         pool[j]["id"], pool[j]["title"], pool[j]["company"], snippet, ""])
    rng.shuffle(rows)  # hide method order from annotators
    with (GOLD / "to_label.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["resume_id", "resume_family", "target_role", "job_id", "job_title", "company", "snippet", "label"])
        wr.writerows(rows)
    print(f"to_label.csv: {len(rows)} pooled pairs for human labelling; done in {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
