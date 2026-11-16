# Learned weights

Split by resume (seed 7): 24 train / 8 validation / 8 test.

- Grid search on validation (maximise NDCG@10): alpha=0.5, beta=0.2, gamma=0.3, delta=0.1 (validation NDCG@10 0.616 vs 0.529 with defaults (0.4, 0.4, 0.2, 0.15)).
- Logistic regression on training pairs (relevant = label >= 2), coefficients sem/skill/context/penalty = 5.625, 6.997, 2.914, 0.806.

| Method (test split) | P@5 | P@10 | R@10 | MRR | NDCG@10 |
|---|---:|---:|---:|---:|---:|
| Keyword Jaccard | 0.250 | 0.300 | 0.408 | 0.403 | 0.432 |
| TF-IDF | 0.300 | 0.287 | 0.390 | 0.627 | 0.458 |
| BM25 | 0.175 | 0.163 | 0.211 | 0.285 | 0.300 |
| SBERT whole-doc | 0.250 | 0.225 | 0.279 | 0.458 | 0.383 |
| SBERT + section-level | 0.275 | 0.263 | 0.343 | 0.375 | 0.404 |
| Ours, default weights | 0.500 | 0.412 | 0.558 | 0.938 | 0.634 |
| Ours, grid-searched weights | 0.500 | 0.450 | 0.601 | 0.604 | 0.601 |
| Ours, logistic-regression weights | 0.525 | 0.425 | 0.576 | 0.729 | 0.622 |
| SBERT whole-doc, fine-tuned encoder | 0.525 | 0.400 | 0.519 | 0.719 | 0.621 |
| Ours + fine-tuned encoder | 0.450 | 0.400 | 0.540 | 1.000 | 0.656 |

Labels: proxy (job-title role family vs resume target role; see docs/report.md). With 8 test resumes these numbers are noisy; the all-resume table is the primary result.
