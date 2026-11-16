"""Assemble docs/report.md from eval/report_template.md and the files in eval/results/.

Sentences that interpret results are generated from summary.json, so re-running the evaluation
(e.g. with human labels) and then this script keeps the prose consistent with the numbers.

Usage (repo root): backend\\.venv\\Scripts\\python.exe eval\\build_report.py
"""

from __future__ import annotations

import json
import re

from common import EVAL, RESULTS, ROOT


def body(name: str) -> str:
    p = RESULTS / name
    if not p.exists():
        return f"_Not generated yet: run the script that writes `eval/results/{name}`._"
    text = p.read_text(encoding="utf-8").strip()
    return re.sub(r"^# .*\n+", "", text, count=1)  # drop the file's own H1


def findings(s: dict) -> dict[str, str]:  # type: ignore[type-arg]
    main = s["main"]
    ours = "Ours (skill-weighted)"
    base = {k: v for k, v in main.items() if k != ours}
    best = max(base, key=lambda k: base[k]["NDCG@10"])
    o, b = main[ours]["NDCG@10"], base[best]["NDCG@10"]
    sig = s["significance"]
    beaten = [k for k, v in sig.items() if v["p_holm"] < 0.05 and v["mean_diff"] > 0]
    not_sig = [k for k, v in sig.items() if not (v["p_holm"] < 0.05 and v["mean_diff"] > 0)]
    ab = s["ablation"]
    full = ab["Ours (full)"]
    deltas = {k: v - full for k, v in ab.items() if k != "Ours (full)"}
    helps = sorted([k for k, d in deltas.items() if d < -0.005], key=lambda k: deltas[k])
    hurts = sorted([k for k, d in deltas.items() if d > 0.005], key=lambda k: -deltas[k])
    neutral = [k for k, d in deltas.items() if abs(d) <= 0.005]
    clean = lambda k: k.lstrip("- ")  # noqa: E731
    lines = {
        "headline": (f"Our skill-weighted model reaches NDCG@10 {o:.3f}, ahead of the best baseline ({best}, {b:.3f}; "
                     f"+{o - b:.3f}). After Holm correction it is significantly better than "
                     f"{', '.join(beaten) or 'none of the baselines'}"
                     + (f", but not significantly better than {', '.join(not_sig)}" if not_sig else "") + "."),
        "ablation": (("Removing these ingredients lowers NDCG@10, so they help: "
                      + "; ".join(f"{clean(k)} ({deltas[k]:+.3f})" for k in helps) + ". ") if helps else "")
                    + (("Removing these raises it, so on these labels they hurt: "
                        + "; ".join(f"{clean(k)} ({deltas[k]:+.3f})" for k in hurts) + ". ") if hurts else "")
                    + (("Little effect either way: " + "; ".join(clean(k) for k in neutral) + ".") if neutral else ""),
        "labels": s["labels"],
        "ours_ndcg": f"{o:.3f}",
        "best_baseline": best,
    }
    return lines


def main() -> None:
    s = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
    f = findings(s)
    lw = s["learned_weights"]
    subs = {
        "main_table": body("main_table.md"), "significance": body("significance.md"), "ablation": body("ablation.md"),
        "learned": body("learned_weights.md"), "per_family": body("per_family.md"), "latency": body("latency.md"),
        "bias": body("bias_check.md"), "campus": body("campus_eval.md"), "agreement": body("agreement.md"),
        "headline": f["headline"], "ablation_findings": f["ablation"], "label_source": f["labels"],
        "ours_ndcg": f["ours_ndcg"], "best_baseline": f["best_baseline"], "n_resumes": str(s["resumes"]),
        "n_jobs": str(s["jobs"]), "rel_per_resume": f"{s['relevant_per_resume']:.1f}",
        "learned_weights": f"alpha={lw['alpha']}, beta={lw['beta']}, gamma={lw['gamma']}, delta={lw['delta']}",
        "learned_source": lw["label_source"],
    }
    text = (EVAL / "report_template.md").read_text(encoding="utf-8")
    for k, v in subs.items():
        text = text.replace("{{" + k + "}}", v)
    missing = re.findall(r"\{\{(\w+)\}\}", text)
    if missing:
        raise SystemExit(f"Unfilled placeholders: {missing}")
    out = ROOT / "docs" / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(text.split())} words)")


if __name__ == "__main__":
    main()
