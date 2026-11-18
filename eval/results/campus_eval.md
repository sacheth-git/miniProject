# Campus evaluation

## Shortlist quality against human judgement

| Drive | Eligible ranked | Human-labelled | P@10 | NDCG@10 | Kendall tau |
|---|---:|---:|---:|---:|---:|
| Nimbus Analytics: Machine Learning Engineer | 44 | 0 | pending | pending | pending |
| Kaveri Systems: Embedded Software Engineer | 43 | 0 | pending | pending | pending |
| BlueOrbit Software: Full Stack Developer | 36 | 0 | pending | pending | pending |
| Deccan Motors: Graduate Engineer Trainee (Design) | 35 | 0 | pending | pending | pending |
| Lakeview FinTech: Data Scientist | 8 | 0 | pending | pending | pending |
| Voltedge Semiconductors: VLSI Design Intern (PPO) | 5 | 0 | pending | pending | pending |

Pending: fill the `label` column (0-3) in `eval/data/shortlist_gold/*.csv` (blind: no names, random order), then re-run this script.

## Fairness on the demo campus

Rates are shortlisted / eligible across drives. Parity is the lowest group rate divided by the highest (below 0.8 deserves a look). Groups under 10 students are hidden. Scores never use name or gender, so blind and named reviews start from the same ranking.

Drives with a shortlist: 3.

**By gender** (parity, system 0.53, actual 0.53)

| Group | Eligible | System top-K rate | Actual shortlist rate |
|---|---:|---:|---:|
| female | 51 | 29.4% | 29.4% |
| male | 71 | 15.5% | 15.5% |

**By branch** (parity, system 0.0, actual 0.0)

| Group | Eligible | System top-K rate | Actual shortlist rate |
|---|---:|---:|---:|
| CSE | 34 | 29.4% | 26.5% |
| ECE | 24 | 33.3% | 33.3% |
| EEE | 26 | 0.0% | 0.0% |
| IT | 17 | 0.0% | 5.9% |
| MECH | 21 | 38.1% | 38.1% |

Blind mode hides names and email in the TPO's view. The score itself never sees name or gender, so the system's recommended set is identical with blind mode on or off; any difference between blind and named reviews comes from the human step, which the time-saved study below measures.

## Time-saved study

Pending. Protocol: 2-3 TPO or faculty volunteers each shortlist 10 from 50 resumes twice (different drives, order counterbalanced): once by hand from the PDFs, once with HireX's ranked, explained list. Record minutes and the chosen roll numbers in `eval/data/time_study.csv`; agreement between the two shortlists and with the system's top 10 is reported alongside the time saved.
