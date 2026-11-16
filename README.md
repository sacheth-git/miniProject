# SkillMatch

Semantic resume–job matching with skill-weighted sentence embeddings, plus a campus placement (TPO) mode.

Upload a resume once. SkillMatch extracts your skills, ranks jobs and internships from legal sources with a
skill-weighted semantic score, explains each score, shows your skill gap, and sends you to the exact original
application page. Jobs from LinkedIn, Indeed and Naukri arrive only through official aggregator APIs
(JSearch / SerpApi Google Jobs), user import, or deep-link search buttons. Nothing is scraped.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Scaffold: FastAPI health check, Vite app, config, tests | done |
| 2 | Resume pipeline: PDF parsing, sections, skills (1,444-entry taxonomy), PII masking | done |
| 3 | Job ingestion: 8 sources, dedup, link checker, scheduler, import, deep links | done |
| 4 | Matching: skill-weighted scorer, FAISS retrieval, 5 baselines, explain, skill gap | done |
| 5 | Frontend: upload, ranked results with filters, apply menu, job details, skill gap, import, tracker, settings | done |
| 5A | Auth: login/register, roles, JWT, multi-tenant isolation, student consent | done |
| 5B | TPO core: bulk import, drives, eligibility with reasons, ranked blind shortlist, exports, audit log | done |
| 5C | Rounds Kanban + results CSV, offers with placement policy, notifications, student campus drives, readiness, unified tracker | done |
| 5D | Placement dashboard, skill-gap heatmap + training recommendations, unplaced students, fairness report, recruiter share links | done |
| 6 | Evaluation: gold-set tooling, baselines, ablation, significance, weight learning, fine-tuning, latency, bias, campus (proxy labels until human labels arrive) | done |
| 7 | Polish and docs | pending |

## Requirements (Windows 11)

- Python 3.11 or 3.12 (`py -0p` lists installed versions)
- Node.js 20+ and npm
- Git

## Setup

Run from the repo root in PowerShell.

```powershell
# 1. Config
Copy-Item .env.example .env        # then fill in any API keys you have

# 2. Backend
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# NLP/ML stack: CPU-only torch first (avoids the multi-GB CUDA build)
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
.\.venv\Scripts\python.exe -m spacy download en_core_web_sm
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

- Frontend: http://localhost:5173 (the System status page calls the backend)
- API docs (OpenAPI): http://127.0.0.1:8000/docs

If PowerShell blocks `Activate.ps1`, you do not need it: the commands above call the venv's `python.exe` directly.

## Accounts and roles

| Role | Gets |
|---|---|
| `job_seeker` | Resume upload, ranked open-market jobs, skill gap, import, tracker |
| `student` | Everything above, plus campus drives (Phase 5B+). Joins a college with the TPO's invite code and explicit consent, which can be withdrawn in Settings |
| `tpo` | Placement office of one institution; sees only that institution's students |
| `recruiter_view` | Read-only shortlist via an expiring share link (Phase 5D) |

Sign-up asks "Are you a campus student?": yes goes to the invite-code step, no makes a job-seeker account.
Placement officers register their institution from the same page. Guests can browse job listings;
everything personal requires signing in. Passwords are hashed with argon2; access tokens last 30 minutes
and refresh automatically; signing out (or changing the password) revokes every session.
Accounts registered with an email in `ADMIN_EMAILS` can run ingestion (`/admin/*`).

## Demo campus

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\seed_demo.py     # ~40 s: 1 institution, 120 synthetic students, 6 drives
```

Everything is synthetic (random name combinations, fictional companies). Logins printed by the script, all with
password `Demo@2026`: placement officer `tpo@demo.skillmatch.example`, students such as
`meera.001@demo.skillmatch.example`. Re-running replaces only the demo institution.

## Placement office (TPO) workflow

1. **Students**: share the invite code, or import a CSV (`roll_no,name,email,branch,batch,cgpa,active_backlogs,tenth,twelfth`)
   plus a ZIP of `{roll_no}.pdf` resumes. The preview flags bad rows (bad CGPA, duplicate roll number, missing resume)
   before anything changes; the import then runs in the background with a progress bar. New students get a temporary
   password (downloadable once) and must set their own, then agree to share their profile.
2. **Drives**: paste or upload the JD; skills and weights are extracted and editable (required / preferred, weight).
   Set eligibility (branches, batch, CGPA, backlogs, 10th / 12th or diploma), rounds and deadline.
3. **Eligibility**: every ineligible student gets explicit reasons ("CGPA 6.8 < 7", "Branch ECE not allowed",
   "Dream rule: drive CTC 10 LPA < 1.5 x current offer 8 LPA"), including the institution's placement policy.
4. **Shortlist**: eligible students ranked by the same skill-weighted score students see. Blind review hides names
   (on by default). Shortlist the top N, everyone above a match %, or tick students by hand; "Why" explains each rank.
5. **Export**: Excel, CSV, PDF summary or a ZIP of resumes, with chosen columns, blind or named.
6. **Rounds**: a Kanban per drive (Applied, Shortlisted, each round, Offer, Accepted, Rejected). Drag a card, move a
   selection, or upload a round's results CSV (`roll_no,result` with pass / fail): passes move to the next round,
   the rest are rejected. Students are notified of every move.
7. **Offers**: record an offer (placement policy is checked), and record decisions students give offline.
8. **Dashboard**: placed % overall, by branch and batch; highest / median / average CTC; offers by company; the
   eligible -> applied -> shortlisted -> offered -> accepted funnel. Every chart has a table view.
9. **Analytics**: a branch x skill heatmap of how many students lack each skill drives require, with training
   recommendations ("50% of CSE students lack Docker, required by 3 drives"); unplaced students with their best-fit
   open drives and open-market jobs; a fairness report of shortlist rates by gender and branch for the system's
   recommendation and the actual shortlist (groups under 10 hidden, parity below 0.8 flagged).
10. **Recruiter share link**: a read-only, expiring page of a drive's shortlist (names hidden by default). Only a hash
    of the link token is stored; links can be revoked and show view counts.
11. **Audit log**: every shortlist edit, stage move, offer, rule change, weight change, import and export, with before /
   after values.

Students see **Campus drives** (eligible first; ineligible ones show the exact reason), apply or withdraw before the
deadline, follow a stage timeline, accept or decline offers, and get a **Readiness** score (match with open drives,
profile completeness, resume ATS checks) with the top 3 things to improve. One **Applications** board shows campus and
open-market applications with a source label. Notifications arrive in-app (bell) and by email when `SMTP_HOST` is set
(printed to the console otherwise): new eligible drive, deadline within 24 h, stage changes, offers.
Accepting an offer marks the student placed, declines their other pending offers and withdraws their other active
campus applications (when "block after accepting" is on). Students can't delete their data while a campus
application is still active; the app tells them why.

SkillMatch recommends; the placement officer makes every decision. Gender, name, photo and college are never used in
scoring, and gender is never available as an eligibility filter.

## Using the app

1. **Home**: drag in a PDF resume. Watch the processing steps, then fix the skill chips and set your target role, locations and job types.
2. **Jobs**: ranked matches with a match ring, matched skills (green) and missing required skills (red). Filter by role, location, remote, job type, experience, source and date. The right panel explains each score.
3. **Apply** opens the job's own application page in a new tab (LinkedIn, Naukri, company site...). When you come back, SkillMatch asks whether you applied and updates your tracker.
4. **Applications**: Kanban tracker (Saved, Ready, Applied, Interview, Offer, Rejected) with drag and drop and notes.
5. **Skill gap**, **Import** (paste a JD or upload alert emails), **Search elsewhere** (LinkedIn / Naukri / Indeed searches), **Settings** (bias-aware toggle, delete my data).

## Tests

```powershell
cd backend;  .\.venv\Scripts\python.exe -m pytest --cov=app
cd frontend; npm test
# End to end against a running API on :8000:
#   e2e.test.tsx         job seeker: sign up -> upload -> results -> apply -> tracker
#   e2e_campus.test.tsx  campus: TPO creates drive -> student applies -> rounds -> offer -> student accepts
#   e2e_analytics.test.tsx  demo campus (seed first): dashboard, analytics, share link -> public page -> revoke
cd frontend; $env:E2E="1"; npx vitest run
```

The first start downloads the embedding model `BAAI/bge-small-en-v1.5` (~130 MB) and warms it up in the background.

## Skill taxonomy

`backend/data/taxonomy/skills.json` merges a curated tech list (`curated_skills.yaml`, ~750 entries with aliases)
with technical skills from the ESCO open taxonomy (European Commission), pulled from the public ESCO API.
The raw ESCO pull is cached in `esco_raw.json`, so rebuilding works offline:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\build_taxonomy.py            # rebuild from cache
.\.venv\Scripts\python.exe scripts\build_taxonomy.py --refresh  # re-download ESCO
.\.venv\Scripts\python.exe scripts\make_sample_resumes.py       # regenerate synthetic sample PDFs
```

## Job ingestion

Sources (official APIs only, nothing is scraped):

| Source | Key | Notes |
|---|---|---|
| Greenhouse, Lever, Ashby | none | Public job-board APIs for the ~150 boards in `backend/data/seeds/companies.yaml` |
| Remotive | none | One call per run (Remotive asks for at most 4 per day) |
| Adzuna, Jooble | yes | Search APIs, India by default |
| JSearch (RapidAPI) | yes | LinkedIn / Indeed / Naukri listings via Google for Jobs, with every `apply_option` kept |
| SerpApi Google Jobs | yes | Optional alternative to JSearch |

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\ingest.py                 # all sources (keyless ones always run)
.\.venv\Scripts\python.exe scripts\ingest.py greenhouse      # one source
.\.venv\Scripts\python.exe scripts\ingest.py --check-links   # mark 404/410 apply URLs inactive
.\.venv\Scripts\python.exe scripts\verify_companies.py       # re-verify / extend the board list
```

While the API runs, the scheduler ingests every 12 h and checks links nightly at 02:30 IST
(`ENABLE_SCHEDULER=false` turns it off). `POST /admin/ingest` starts a run;
`GET /admin/sources/status` shows per-source counts, last run and errors.
Responses are cached for 6 h in `backend/data/cache/http/`. The link checker never requests
LinkedIn, Indeed, Naukri or Glassdoor pages; those listings expire through the source API.

## Matching

```
S = a*Sem + b*Skill + g*Context - d*Penalty          (defaults 0.4 / 0.4 / 0.2 / 0.15)
Sem     = 0.7 * max over resume sections cos(section, JD responsibilities) + 0.3 * cos(resume, JD)
Skill   = sum_j w_j * best_j / sum_j w_j,  w_j = type_j (1.0 required, 0.5 preferred) * idf_j
Penalty = share of required skills with no match >= 0.5
```

Cosines are calibrated per embedding model (`app/matching/calibration.py`): bge-small scores unrelated
skill names at 0.56-0.65, so the raw 0.5 cut-off would credit everything.

```powershell
cd backend
.\.venv\Scripts\python.exe scriptsuild_index.py    # embed jobs + build FAISS index (first run ~1 h on CPU, resumable)
.\.venv\Scripts\python.exe scriptsench_match.py    # latency benchmark on the real index
```

Endpoints: `GET /match/{candidate_id}?method=ours|tfidf|bm25|keyword_jaccard|sbert_whole|sbert_section`,
`GET /match/{candidate_id}/{job_id}/explain`, `GET /gap/{candidate_id}`. Ingestion rebuilds the index automatically.

## Evaluation

See `eval/README.md` for the run order and `docs/report.md` for the results. The current numbers use
title-based proxy labels; label the pooled pairs with `eval/label_app.py` and re-run to replace them.

## Database migrations

```powershell
cd backend
.\.venv\Scripts\alembic.exe revision --autogenerate -m "message"
.\.venv\Scripts\alembic.exe upgrade head
```

SQLite is the dev default (`backend/skillmatch.db`). Set `DATABASE_URL` in `.env` for PostgreSQL.

## API keys

All keys are optional. A source without a key is skipped and logged as a warning.

| Variable | Service | Where to get it | Cost |
|---|---|---|---|
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Adzuna job search (India + others) | https://developer.adzuna.com/ | Free tier |
| `JOOBLE_KEY` | Jooble aggregator | https://jooble.org/api/about | Free |
| `RAPIDAPI_KEY` | JSearch (LinkedIn / Indeed / Naukri via Google for Jobs) | https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch | Free tier, paid above quota |
| `SERPAPI_KEY` | SerpApi Google Jobs (optional alternative) | https://serpapi.com/ | Free tier, paid above quota |

Greenhouse, Lever, Ashby and Remotive need no key.

## Layout

```
backend/   FastAPI app, models, NLP pipeline, ingestion, tests
frontend/  React + Vite + TypeScript + Tailwind
eval/      notebooks, scripts, results
docs/      report, IEEE paper, architecture
```
