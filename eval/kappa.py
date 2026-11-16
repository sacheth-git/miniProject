"""Inter-annotator agreement over eval/data/gold/labels_*.csv.

Cohen's kappa (unweighted and quadratic-weighted) for every annotator pair, Fleiss' kappa
when three or more annotators labelled the same pairs. Writes eval/results/agreement.md.

Usage (repo root): backend\\.venv\\Scripts\\python.exe eval\\kappa.py
"""

from __future__ import annotations

import csv
import itertools

import numpy as np
from sklearn.metrics import cohen_kappa_score

from common import GOLD, RESULTS


def load() -> dict[str, dict[tuple[str, str], int]]:
    out: dict[str, dict[tuple[str, str], int]] = {}
    for p in sorted(GOLD.glob("labels_*.csv")):
        name = p.stem.removeprefix("labels_")
        out[name] = {(r["resume_id"], r["job_id"]): int(r["label"]) for r in csv.DictReader(p.open(encoding="utf-8")) if r["label"] != ""}
    return out


def fleiss(matrix: np.ndarray) -> float:
    """matrix: items x categories counts, same number of raters per item."""
    n = matrix.sum(axis=1)[0]
    p_j = matrix.sum(axis=0) / matrix.sum()
    p_i = ((matrix * (matrix - 1)).sum(axis=1)) / (n * (n - 1))
    p_bar, p_e = p_i.mean(), (p_j ** 2).sum()
    return float((p_bar - p_e) / (1 - p_e)) if p_e < 1 else 1.0


def main() -> None:
    labels = load()
    lines = ["# Inter-annotator agreement", ""]
    if len(labels) < 2:
        lines.append(f"Need labels from at least two annotators (found {len(labels)}: {', '.join(labels) or 'none'}). "
                     "Run eval/label_app.py with different --annotator names on the same pairs.")
    else:
        lines += ["| Pair | Items | Cohen's kappa | Weighted (quadratic) |", "|---|---:|---:|---:|"]
        for a, b in itertools.combinations(labels, 2):
            common = sorted(set(labels[a]) & set(labels[b]))
            if len(common) < 10:
                lines.append(f"| {a} vs {b} | {len(common)} | too few | too few |")
                continue
            x = [labels[a][k] for k in common]
            y = [labels[b][k] for k in common]
            lines.append(f"| {a} vs {b} | {len(common)} | {cohen_kappa_score(x, y):.3f} | {cohen_kappa_score(x, y, weights='quadratic'):.3f} |")
        if len(labels) >= 3:
            common = sorted(set.intersection(*(set(v) for v in labels.values())))
            if common:
                m = np.zeros((len(common), 4))
                for i, k in enumerate(common):
                    for v in labels.values():
                        m[i, v[k]] += 1
                lines += ["", f"Fleiss' kappa over {len(common)} items labelled by all {len(labels)} annotators: **{fleiss(m):.3f}**"]
        lines += ["", "Interpretation (Landis & Koch): < 0.20 slight, 0.21-0.40 fair, 0.41-0.60 moderate, 0.61-0.80 substantial, > 0.80 almost perfect."]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "agreement.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
