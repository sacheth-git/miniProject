# Evaluation

Run from the repo root with the backend virtual environment (`backend\.venv\Scripts\python.exe`). The job index
must exist (`backend\scripts\build_index.py`) and, for the campus part, the demo seed (`backend\scripts\seed_demo.py`).

| Step | Script | Output |
|---|---|---|
| 1. Gold set | `eval\build_gold.py` | 40 synthetic resumes (`data/resumes`), 200-job pool, cached features, proxy labels, `data/gold/to_label.csv` |
| 2. Human labels (optional, recommended) | `eval\label_app.py --annotator <name>` (run by 2-3 people) | `data/gold/labels_<name>.csv` |
| 3. Agreement | `eval\kappa.py` | `results/agreement.md` (Cohen's, weighted, Fleiss' kappa) |
| 4. Fine-tune (optional, ~45 min CPU) | `eval\finetune.py` | `models/finetuned-eval/`, `data/features_ft.npz` |
| 5. Ranking evaluation | `eval\evaluate.py` | main table, significance, ablation, learned weights, per-role table, charts |
| 6. Latency | `eval\latency.py` | `results/latency.md`, `latency.png` |
| 7. Bias check | `eval\bias_check.py` | `results/bias_check.md` |
| 8. Campus (section J) | `eval\shortlist_quality.py` | `results/campus_eval.md`, blind templates in `data/shortlist_gold/`, `data/time_study.csv` |
| 9. Report | `eval\build_report.py` | `docs/report.md` |

`evaluate.py` uses human labels automatically when `data/gold/labels_*.csv` exist (majority vote; unlabelled pooled
pairs count as not relevant), otherwise the title-based proxy labels. Weights learned from human labels are written
to `backend/data/learned_weights.json` and used by the app; proxy-learned weights are reported only.

`analysis.ipynb` shows the result tables and charts in a notebook.
