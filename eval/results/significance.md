# Significance: ours vs each baseline

Paired two-sided Wilcoxon signed-rank test over 40 resumes on NDCG@10, Holm-corrected for the number of comparisons.

| Ours vs | Mean NDCG@10 difference | Wins / ties / losses | p (Wilcoxon) | p (Holm-adjusted) |
|---|---:|---:|---:|---:|
| Keyword Jaccard | +0.129 | 31 / 0 / 9 | 6.3e-05 | 0.00025 |
| TF-IDF | +0.076 | 25 / 0 / 15 | 0.0086 | 0.026 |
| BM25 | +0.230 | 36 / 0 / 4 | 1.4e-09 | 6.9e-09 |
| SBERT whole-doc | +0.062 | 26 / 0 / 14 | 0.087 | 0.087 |
| SBERT + section-level | +0.090 | 25 / 0 / 15 | 0.012 | 0.026 |
