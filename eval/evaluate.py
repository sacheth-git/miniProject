"""Ranking evaluation: baselines, ablations, weight learning, significance, charts.

Labels: human labels (eval/data/gold/labels_*.csv, majority vote; unlabelled pooled pairs count as 0)
when present, otherwise the title-based proxy labels. Pass --labels proxy|human to force one.

Usage (repo root): backend\\.venv\\Scripts\\python.exe eval\\evaluate.py
Outputs: eval/results/{main_table,ablation,learned_weights,significance}.{md,csv}, *.png, summary.json
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

from common import BACKEND, DATA, GOLD, METRICS, RESULTS, all_metrics, load_json, np

SEED = 7
W0 = (0.4, 0.4, 0.2, 0.15)


def load_labels(source: str, resume_ids: list[str], job_ids: list[str]) -> tuple[np.ndarray, str]:
    ri = {r: i for i, r in enumerate(resume_ids)}
    ji = {j: i for i, j in enumerate(job_ids)}
    human = sorted(GOLD.glob("labels_*.csv"))
    use_human = source == "human" or (source == "auto" and human)
    y = np.zeros((len(resume_ids), len(job_ids)), dtype=np.float32)
    if use_human:
        votes: dict[tuple[str, str], list[int]] = defaultdict(list)
        for p in human:
            for r in csv.DictReader(p.open(encoding="utf-8")):
                if r["label"] != "":
                    votes[(r["resume_id"], r["job_id"])].append(int(r["label"]))
        for (r, j), v in votes.items():
            if r in ri and j in ji:
                y[ri[r], ji[j]] = Counter(v).most_common(1)[0][0]
        return y, f"human ({len(human)} annotator file(s), {len(votes)} labelled pairs; unlabelled pairs = 0)"
    for r in csv.DictReader((GOLD / "proxy_labels.csv").open(encoding="utf-8")):
        if r["resume_id"] in ri:
            y[ri[r["resume_id"]], ji[r["job_id"]]] = int(r["label"])
    return y, "proxy (job-title role family vs resume target role; see docs/report.md)"


def combine(f: dict[str, np.ndarray], w: tuple[float, float, float, float], sem: str = "sem", skill: str = "skill_full",
            pen: str = "pen_full") -> np.ndarray:
    a, b, g, d = w
    return a * f[sem] + b * f[skill] + g * f["context"] - d * f[pen]


def per_resume(scores: np.ndarray, y: np.ndarray, rows: list[int]) -> dict[str, np.ndarray]:
    out: dict[str, list[float]] = {m: [] for m in METRICS}
    for i in rows:
        for m, v in all_metrics(scores[i], y[i]).items():
            out[m].append(v)
    return {m: np.array(v) for m, v in out.items()}


def bootstrap_ci(x: np.ndarray, n: int = 2000, seed: int = SEED) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    out, running = {}, 0.0
    for k, (name, p) in enumerate(items):
        running = max(running, min(1.0, (len(items) - k) * p))
        out[name] = running
    return out


def grid_search(f: dict[str, np.ndarray], y: np.ndarray, rows: list[int]) -> tuple[tuple[float, float, float, float], float]:
    best, best_v = W0, -1.0
    steps = [round(x * 0.1, 1) for x in range(11)]
    for a, b in itertools.product(steps, steps):
        g = round(1 - a - b, 1)
        if g < 0:
            continue
        for d in (0.0, 0.05, 0.1, 0.15, 0.2, 0.3):
            v = per_resume(combine(f, (a, b, g, d)), y, rows)["NDCG@10"].mean()
            if v > best_v + 1e-9:
                best, best_v = (a, b, g, d), float(v)
    return best, best_v


def logreg_weights(f: dict[str, np.ndarray], y: np.ndarray, rows: list[int]) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression

    X = np.stack([f["sem"][rows].ravel(), f["skill_full"][rows].ravel(), f["context"][rows].ravel(), f["pen_full"][rows].ravel()], 1)
    t = (y[rows].ravel() >= 2).astype(int)
    if t.sum() == 0 or t.sum() == len(t):
        return np.array(W0)
    clf = LogisticRegression(max_iter=2000, class_weight="balanced").fit(X, t)
    return clf.coef_[0]


def fmt(v: float) -> str:
    return f"{v:.3f}"


def bar_chart(path: Path, names: list[str], means: list[float], lo: list[float], hi: list[float], title: str, highlight: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 0.42 * len(names) + 1.2), dpi=150)
    ypos = np.arange(len(names))[::-1]
    colors = ["#2a78d6" if n == highlight else "#9ec5f4" for n in names]
    ax.barh(ypos, means, color=colors, height=0.55, xerr=[np.array(means) - lo, np.array(hi) - np.array(means)],
            error_kw={"ecolor": "#52514e", "elinewidth": 1, "capsize": 2})
    for yp, m in zip(ypos, means):
        ax.text(m + 0.01, yp, f"{m:.3f}", va="center", fontsize=8, color="#0b0b0b")
    ax.set_yticks(ypos, names, fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_xlabel("NDCG@10 (mean over resumes, 95% bootstrap CI)", fontsize=9)
    ax.set_title(title, fontsize=10, loc="left")
    ax.grid(axis="x", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", choices=["auto", "proxy", "human"], default="auto")
    args = ap.parse_args()
    raw = np.load(DATA / "features.npz")
    parsed = load_json(DATA / "parsed.json")
    keep = [i for i, p in enumerate(parsed) if p["bias_aware"]]  # evaluation uses the bias-aware (default) pipeline
    f = {k: raw[k][keep] for k in raw.files if k not in ("resume_ids", "job_ids")}
    resume_ids = [parsed[i]["id"] for i in keep]
    families = [parsed[i]["family"] for i in keep]
    y, label_note = load_labels(args.labels, resume_ids, list(raw["job_ids"]))
    n = len(resume_ids)
    all_rows = list(range(n))

    ft_path = DATA / "features_ft.npz"
    ft = None
    if ft_path.exists():
        rft = np.load(ft_path)
        ft = {k: rft[k] for k in rft.files if k not in ("resume_ids", "job_ids")}

    methods: dict[str, np.ndarray] = {
        "Keyword Jaccard": f["jaccard"],
        "TF-IDF": f["tfidf"],
        "BM25": f["bm25"],
        "SBERT whole-doc": f["sem_full_raw"],
        "SBERT + section-level": f["sem"],
        "Ours (skill-weighted)": combine(f, W0),
    }
    ablations: dict[str, np.ndarray] = {
        "Ours (full)": combine(f, W0),
        "- section-level semantics (whole doc only)": combine(f, W0, sem="sem_full"),
        "- skill term": combine(f, (W0[0], 0.0, W0[2], W0[3])),
        "- IDF weighting": combine(f, W0, skill="skill_no_idf", pen="pen_no_idf"),
        "- required/preferred weighting": combine(f, W0, skill="skill_no_type", pen="pen_no_type"),
        "- IDF and type weighting": combine(f, W0, skill="skill_flat", pen="pen_flat"),
        "- soft skill match (exact only)": combine(f, W0, skill="skill_hard", pen="pen_hard"),
        "- shrinkage for thin JDs": combine(f, W0, skill="skill_no_shrink", pen="pen_no_shrink"),
        "- context fit": combine(f, (W0[0], W0[1], 0.0, W0[3])),
        "- missing-skill penalty": combine(f, (W0[0], W0[1], W0[2], 0.0)),
        "- cosine calibration": combine(f, W0, sem="sem_raw", skill="skill_no_cal", pen="pen_no_cal"),
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"labels": label_note, "resumes": n, "jobs": int(y.shape[1]),
                                  "relevant_per_resume": float((y >= 2).sum(axis=1).mean())}

    # ---------- main table (all resumes, default weights: nothing tuned) ----------
    per = {name: per_resume(s, y, all_rows) for name, s in methods.items()}
    ours_key = "Ours (skill-weighted)"
    rows_md = ["| Method | " + " | ".join(METRICS) + " |", "|---|" + "---:|" * len(METRICS)]
    csv_rows = []
    for name, res in per.items():
        cells = []
        for m in METRICS:
            lo, hi = bootstrap_ci(res[m])
            cells.append(f"{res[m].mean():.3f} [{lo:.2f}, {hi:.2f}]")
            csv_rows.append({"method": name, "metric": m, "mean": round(float(res[m].mean()), 4), "ci_low": round(lo, 4), "ci_high": round(hi, 4)})
        bold = name == ours_key
        rows_md.append(f"| {'**' + name + '**' if bold else name} | " + " | ".join(cells) + " |")
    (RESULTS / "main_table.md").write_text(
        f"# Ranking quality (all {n} resumes, default weights {W0})\n\nLabels: {label_note}. Relevant = label >= 2; "
        f"NDCG uses graded labels. Mean [95% bootstrap CI] over resumes.\n\n" + "\n".join(rows_md) + "\n", encoding="utf-8")
    with (RESULTS / "main_table.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["method", "metric", "mean", "ci_low", "ci_high"])
        w.writeheader()
        w.writerows(csv_rows)

    # ---------- significance: ours vs every baseline (paired Wilcoxon on per-resume NDCG@10) ----------
    from scipy.stats import wilcoxon

    pvals, diffs = {}, {}
    for name in methods:
        if name == ours_key:
            continue
        a, b = per[ours_key]["NDCG@10"], per[name]["NDCG@10"]
        d = a - b
        diffs[name] = float(d.mean())
        pvals[name] = 1.0 if np.allclose(d, 0) else float(wilcoxon(a, b, zero_method="wilcox", alternative="two-sided").pvalue)
    adj = holm(pvals)
    sig_md = ["| Ours vs | Mean NDCG@10 difference | Wins / ties / losses | p (Wilcoxon) | p (Holm-adjusted) |", "|---|---:|---:|---:|---:|"]
    for name in pvals:
        d = per[ours_key]["NDCG@10"] - per[name]["NDCG@10"]
        wtl = f"{int((d > 1e-9).sum())} / {int((abs(d) <= 1e-9).sum())} / {int((d < -1e-9).sum())}"
        sig_md.append(f"| {name} | {diffs[name]:+.3f} | {wtl} | {pvals[name]:.2g} | {adj[name]:.2g} |")
    (RESULTS / "significance.md").write_text(
        f"# Significance: ours vs each baseline\n\nPaired two-sided Wilcoxon signed-rank test over {n} resumes on NDCG@10, "
        "Holm-corrected for the number of comparisons.\n\n" + "\n".join(sig_md) + "\n", encoding="utf-8")
    summary["significance"] = {k: {"mean_diff": diffs[k], "p": pvals[k], "p_holm": adj[k]} for k in pvals}

    # ---------- ablation ----------
    per_ab = {name: per_resume(s, y, all_rows) for name, s in ablations.items()}
    full = per_ab["Ours (full)"]["NDCG@10"].mean()
    ab_md = ["| Variant | NDCG@10 | Delta vs full | P@10 | MRR |", "|---|---:|---:|---:|---:|"]
    ab_csv = []
    for name, res in per_ab.items():
        v = res["NDCG@10"].mean()
        ab_md.append(f"| {name} | {v:.3f} | {v - full:+.3f} | {res['P@10'].mean():.3f} | {res['MRR'].mean():.3f} |")
        ab_csv.append({"variant": name, "ndcg10": round(float(v), 4), "delta": round(float(v - full), 4),
                       "p10": round(float(res["P@10"].mean()), 4), "mrr": round(float(res["MRR"].mean()), 4)})
    (RESULTS / "ablation.md").write_text(
        f"# Ablation (all {n} resumes, default weights)\n\nEach row removes one ingredient from the full model.\n\n" + "\n".join(ab_md) + "\n",
        encoding="utf-8")
    with (RESULTS / "ablation.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ab_csv[0]))
        w.writeheader()
        w.writerows(ab_csv)

    # ---------- weight learning: 60/20/20 split by resume ----------
    rng = np.random.default_rng(SEED)
    order = rng.permutation(n).tolist()
    n_tr, n_va = round(0.6 * n), round(0.2 * n)
    train, val, test = order[:n_tr], order[n_tr:n_tr + n_va], order[n_tr + n_va:]
    w_grid, v_grid = grid_search(f, y, val)
    v_default = per_resume(combine(f, W0), y, val)["NDCG@10"].mean()
    coef = logreg_weights(f, y, train)
    lr_scores = coef[0] * f["sem"] + coef[1] * f["skill_full"] + coef[2] * f["context"] + coef[3] * f["pen_full"]
    test_methods = {**{k: methods[k] for k in methods if k != ours_key}, "Ours, default weights": combine(f, W0),
                    "Ours, grid-searched weights": combine(f, w_grid), "Ours, logistic-regression weights": lr_scores}
    if ft is not None:  # fine-tuned on the training split only, so it is reported on the test split only
        test_methods["SBERT whole-doc, fine-tuned encoder"] = ft["sem_full_raw"]
        test_methods["Ours + fine-tuned encoder"] = combine(ft, W0)
    tm_md = ["| Method (test split) | " + " | ".join(METRICS) + " |", "|---|" + "---:|" * len(METRICS)]
    for name, s in test_methods.items():
        res = per_resume(s, y, test)
        tm_md.append(f"| {name} | " + " | ".join(fmt(res[m].mean()) for m in METRICS) + " |")
    (RESULTS / "learned_weights.md").write_text(
        f"# Learned weights\n\nSplit by resume (seed {SEED}): {len(train)} train / {len(val)} validation / {len(test)} test.\n\n"
        f"- Grid search on validation (maximise NDCG@10): alpha={w_grid[0]}, beta={w_grid[1]}, gamma={w_grid[2]}, delta={w_grid[3]} "
        f"(validation NDCG@10 {v_grid:.3f} vs {v_default:.3f} with defaults {W0}).\n"
        f"- Logistic regression on training pairs (relevant = label >= 2), coefficients sem/skill/context/penalty = "
        f"{', '.join(f'{c:.3f}' for c in coef)}.\n\n" + "\n".join(tm_md) +
        f"\n\nLabels: {label_note}. With {len(test)} test resumes these numbers are noisy; the all-resume table is the primary result.\n",
        encoding="utf-8")
    learned = {"alpha": w_grid[0], "beta": w_grid[1], "gamma": w_grid[2], "delta": w_grid[3], "val_ndcg10": v_grid,
               "default_val_ndcg10": float(v_default), "label_source": "human" if label_note.startswith("human") else "proxy"}
    (BACKEND / "data").mkdir(exist_ok=True)
    (BACKEND / "data" / "learned_weights.json").write_text(json.dumps(learned, indent=1), encoding="utf-8")
    summary["learned_weights"] = learned

    # ---------- charts ----------
    names = list(per)
    bar_chart(RESULTS / "ndcg_by_method.png", names, [per[k]["NDCG@10"].mean() for k in names],
              [bootstrap_ci(per[k]["NDCG@10"])[0] for k in names], [bootstrap_ci(per[k]["NDCG@10"])[1] for k in names],
              "Ranking quality by method", ours_key)
    ab_names = list(per_ab)
    bar_chart(RESULTS / "ablation.png", ab_names, [per_ab[k]["NDCG@10"].mean() for k in ab_names],
              [bootstrap_ci(per_ab[k]["NDCG@10"])[0] for k in ab_names], [bootstrap_ci(per_ab[k]["NDCG@10"])[1] for k in ab_names],
              "Ablation: removing one ingredient at a time", "Ours (full)")

    # ---------- per-family breakdown ----------
    fam_rows = ["| Target role | Ours NDCG@10 | Best baseline | Its NDCG@10 |", "|---|---:|---|---:|"]
    for fam in sorted(set(families)):
        rows = [i for i in all_rows if families[i] == fam]
        ours_v = per_resume(methods[ours_key], y, rows)["NDCG@10"].mean()
        base = {k: per_resume(methods[k], y, rows)["NDCG@10"].mean() for k in methods if k != ours_key and "fine-tuned" not in k}
        bk = max(base, key=base.get)  # type: ignore[arg-type]
        fam_rows.append(f"| {fam} | {ours_v:.3f} | {bk} | {base[bk]:.3f} |")
    (RESULTS / "per_family.md").write_text("# NDCG@10 by target role\n\n" + "\n".join(fam_rows) + "\n", encoding="utf-8")

    summary["main"] = {k: {m: float(v[m].mean()) for m in METRICS} for k, v in per.items()}
    summary["ablation"] = {k: float(v["NDCG@10"].mean()) for k, v in per_ab.items()}
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for p in ("main_table.md", "significance.md", "ablation.md", "learned_weights.md", "per_family.md"):
        print((RESULTS / p).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
