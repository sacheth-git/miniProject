# Ablation (all 40 resumes, default weights)

Each row removes one ingredient from the full model.

| Variant | NDCG@10 | Delta vs full | P@10 | MRR |
|---|---:|---:|---:|---:|
| Ours (full) | 0.552 | +0.000 | 0.358 | 0.789 |
| - section-level semantics (whole doc only) | 0.518 | -0.034 | 0.312 | 0.809 |
| - skill term | 0.559 | +0.006 | 0.380 | 0.702 |
| - IDF weighting | 0.554 | +0.002 | 0.362 | 0.789 |
| - required/preferred weighting | 0.560 | +0.008 | 0.370 | 0.784 |
| - IDF and type weighting | 0.556 | +0.004 | 0.367 | 0.789 |
| - soft skill match (exact only) | 0.525 | -0.028 | 0.340 | 0.754 |
| - shrinkage for thin JDs | 0.525 | -0.027 | 0.340 | 0.772 |
| - context fit | 0.507 | -0.046 | 0.323 | 0.721 |
| - missing-skill penalty | 0.602 | +0.050 | 0.403 | 0.782 |
| - cosine calibration | 0.560 | +0.008 | 0.372 | 0.754 |
