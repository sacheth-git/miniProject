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
| 2 | Resume pipeline | pending |
| 3 | Job ingestion | pending |
| 4 | Matching, baselines, explain, gap | pending |
| 5 | Frontend | pending |
| 5A–5D | Auth, TPO mode, drives, analytics | pending |
| 6 | Evaluation | pending |
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
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
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

## Tests

```powershell
cd backend;  .\.venv\Scripts\python.exe -m pytest --cov=app
cd frontend; npm test
```

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
