"""Fine-tune the sentence encoder on positive resume-JD pairs (training split only).

MultipleNegativesRankingLoss with in-batch negatives. The model is saved to
models/finetuned-eval/ (NOT models/finetuned/, which the live app would load automatically),
then features for the gold set are recomputed with it into eval/data/features_ft.npz.
To use it in the app, copy it to models/finetuned/ and rebuild the job index.

Usage (repo root): backend\\.venv\\Scripts\\python.exe eval\\finetune.py [--epochs 2]
"""

from __future__ import annotations

import argparse
import random
import time

from common import DATA, ROOT, load_json, np

OUT = ROOT / "models" / "finetuned-eval"
SEED = 7


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch", type=int, default=16)
    args = ap.parse_args()
    from sentence_transformers import InputExample, SentenceTransformer, losses
    from sqlalchemy import select
    from torch.utils.data import DataLoader

    from app.core.config import get_settings
    from app.core.db import SessionLocal
    from app.core.logging import configure_logging
    from app.embeddings.documents import job_document
    from app.embeddings.encoder import Encoder
    from app.models.job import Job
    from build_gold import compute_features
    from evaluate import load_labels

    configure_logging("WARNING")
    random.seed(SEED)
    parsed = load_json(DATA / "parsed.json")
    pool = load_json(DATA / "pool.json")
    keep = [p for p in parsed if p["bias_aware"]]
    y, note = load_labels("auto", [p["id"] for p in keep], [p["id"] for p in pool])
    n = len(keep)
    order = np.random.default_rng(SEED).permutation(n).tolist()  # same split as evaluate.py
    train = order[: round(0.6 * n)]
    with SessionLocal() as db:
        jobs = {j.id: j for j in db.scalars(select(Job).where(Job.id.in_([p["id"] for p in pool])))}
    examples = []
    for i in train:
        text = keep[i]["masked_text"] or keep[i]["raw_text"]
        for j in np.where(y[i] >= 2)[0]:
            jb = jobs[pool[j]["id"]]
            examples.append(InputExample(texts=[text, job_document(jb.title, jb.description)]))
    random.shuffle(examples)
    print(f"{len(examples)} positive pairs from {len(train)} training resumes (labels: {note})")
    t0 = time.perf_counter()
    model = SentenceTransformer(get_settings().embedding_model, device="cpu")
    loader = DataLoader(examples, shuffle=True, batch_size=args.batch)
    loss = losses.MultipleNegativesRankingLoss(model)
    model.fit(train_objectives=[(loader, loss)], epochs=args.epochs, warmup_steps=max(1, len(loader) // 10), show_progress_bar=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(OUT))
    print(f"fine-tuned in {time.perf_counter() - t0:.0f}s -> {OUT}")

    enc = Encoder(str(OUT), None)  # own cache namespace (model name = path)
    feats = compute_features(parsed, pool, encoder=enc, use_index_vectors=False)
    keep_idx = [i for i, p in enumerate(parsed) if p["bias_aware"]]
    np.savez_compressed(DATA / "features_ft.npz", **{k: v[keep_idx] for k, v in feats.items()})
    print(f"features_ft.npz written ({time.perf_counter() - t0:.0f}s total)")


if __name__ == "__main__":
    main()
