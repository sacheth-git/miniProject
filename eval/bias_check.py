"""Bias check: how much do names, contact details, gender words and college change the ranking?

Every gold resume was parsed twice (bias-aware masking on and off). For each resume we rank the
same 200-job pool both ways and report Kendall tau, top-10 overlap and the score shift. Tau close
to 1 means personal details barely move the ranking.

Usage (repo root): backend\\.venv\\Scripts\\python.exe eval\\bias_check.py
"""

from __future__ import annotations

from common import DATA, RESULTS, kendall_tau, load_json, np, ranks_desc

W0 = (0.4, 0.4, 0.2, 0.15)


def main() -> None:
    raw = np.load(DATA / "features.npz")
    parsed = load_json(DATA / "parsed.json")
    f = {k: raw[k] for k in raw.files if k not in ("resume_ids", "job_ids")}
    score = W0[0] * f["sem"] + W0[1] * f["skill_full"] + W0[2] * f["context"] - W0[3] * f["pen_full"]
    idx = {p["id"]: i for i, p in enumerate(parsed)}
    taus, overlaps, shifts, whole_taus = [], [], [], []
    for p in parsed:
        if not p["bias_aware"]:
            continue
        a, b = idx[p["id"]], idx[f"{p['id']}-raw"]
        taus.append(kendall_tau(score[a], score[b]))
        whole_taus.append(kendall_tau(f["sem_full_raw"][a], f["sem_full_raw"][b]))
        overlaps.append(len(set(ranks_desc(score[a])[:10]) & set(ranks_desc(score[b])[:10])) / 10)
        shifts.append(float(np.abs(score[a] - score[b]).mean()))
    t, o, s, wt = map(np.array, (taus, overlaps, shifts, whole_taus))
    md = [
        "# Bias check: masked vs unmasked resumes",
        "",
        f"{len(t)} resumes x 200 jobs, our scorer with default weights.",
        "",
        "| Measure | Mean | Min |",
        "|---|---:|---:|",
        f"| Kendall tau, full ranking | {t.mean():.3f} | {t.min():.3f} |",
        f"| Top-10 overlap | {o.mean():.2f} | {o.min():.2f} |",
        f"| Mean absolute score change | {s.mean():.4f} | - |",
        f"| Kendall tau, SBERT whole-doc baseline (for comparison) | {wt.mean():.3f} | {wt.min():.3f} |",
        "",
        "Masking replaces name, email, phone, profile links, gendered words and college name before embedding. "
        "A tau near 1 says those details barely influence the ranking; whatever influence remains comes from the "
        "whole-resume embedding, which is why bias-aware mode is on by default.",
    ]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "bias_check.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
