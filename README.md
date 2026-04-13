# Cutline

A daily MLB grid trivia game. Each day, players see one category (e.g. "Won NL MVP")
and a 3×3 grid of 9 player names. Some are genuine qualifiers; a few are
**imposters** — names that _feel_ like they should qualify but don't. Tap the
names you believe are real, submit, and see how you did.

The core appeal is the "tip of your tongue" cognitive tension: you _almost_
know the answer, and the imposters are designed to trip you up.

## Repository layout

```
cutline/
├── backend/         # FastAPI + async SQLAlchemy + Alembic
│   ├── app/         # Application code
│   ├── alembic/     # Database migrations
│   ├── scripts/     # Data ingestion + sample seed
│   └── tests/       # pytest suite (scoring, API)
├── frontend/        # Next.js app (App Router, TypeScript, Tailwind)
│   ├── app/         # Routes
│   ├── components/  # UI components
│   └── lib/         # API client, session, share
└── docker-compose.yml
```

## Scoring

Each card is a tri-state mark: **YES** (you think it qualifies), **NO** (you
think it's an imposter), or **blank** (unsure). Tap to cycle blank → YES → NO
→ blank.

|                | Qualifier          | Imposter          |
| -------------- | ------------------ | ----------------- |
| 🟢 YES (green) | **+1** correct      | **−1** false positive |
| 🔴 NO (red)    | **−1** wrong reject | **+1** correct identify |
| ⚪ Blank        | 0                  | 0                 |

Max score = **9** (one point per confident-and-right answer). Min = −9.
Blanks are free, so cautious play is viable.

## Quick start

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# Option A: run against local Postgres
export DATABASE_URL=postgresql+asyncpg://cutline:cutline@localhost:5432/cutline
alembic upgrade head
python -m scripts.seed_sample

# Option B: in-memory SQLite (no Postgres needed — tests + local play)
export DATABASE_URL=sqlite+aiosqlite:///./cutline.db
alembic upgrade head
python -m scripts.seed_sample

uvicorn app.main:app --reload
```

Backend serves on `http://localhost:8000`. OpenAPI docs at `/docs`.

### Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
```

Frontend serves on `http://localhost:3000`.

### Docker

```bash
docker-compose up -d postgres
```

## Data pipeline

Primary source: [Chadwick Bureau Lahman Baseball Database](https://github.com/chadwickbureau/baseballdatabank).

```bash
# Option A: a directory of CSVs (e.g. a clone of baseballdatabank)
python -m scripts.ingest_lahman --path ../data/baseballdatabank

# Option B: a zip archive — no unzip step needed
python -m scripts.ingest_lahman --zip  ../data/baseballdatabank-2024.zip
```

The ingest loads `People.csv`, `AwardsPlayers.csv`, `Batting.csv`, `Pitching.csv`,
`AllstarFull.csv`, and `Appearances.csv` into the normalized schema.

Lahman only tracks award _winners_ by default. For imposter generation
(near-miss candidates), supplemental voting data from Baseball Reference is
needed — see `backend/app/categories.py` for the hooks.

## API

| Method | Path                          | Description                                  |
| ------ | ----------------------------- | -------------------------------------------- |
| GET    | `/api/puzzle/today`           | Today's puzzle (category + 9 names)          |
| POST   | `/api/puzzle/submit`          | Submit selections, return score + reveal    |
| GET    | `/api/puzzle/stats`           | Aggregate completion + average score         |
| GET    | `/api/puzzle/{date}`          | Archive access (past puzzles)                |
| GET    | `/api/puzzle/streak`          | Player's current streak data                 |
| POST   | `/api/admin/puzzle`           | Create/schedule a puzzle                     |
| GET    | `/api/admin/puzzle/preview`   | Preview a puzzle before publishing           |
| GET    | `/api/admin/categories`       | List registered category types               |
| GET    | `/api/admin/players/search`   | Search players for puzzle building           |

## Tests

```bash
cd backend
pytest
```

## Status

MVP scaffold covering the full design spec:

- ✅ Schema (players, awards, stats, all-star, teams, puzzles, entries, submissions)
- ✅ Scoring engine (+1 / −1) and share-grid generator
- ✅ Category registry with SQL hooks for qualifier/imposter pools
- ✅ Puzzle + submission API
- ✅ Admin endpoints for puzzle CRUD and preview
- ✅ Sample seed with a hand-curated "Won NL MVP" puzzle
- ✅ Next.js frontend: puzzle screen, reveal, share, localStorage session
- ✅ Lahman ingestion skeleton
- ⏳ Lahman voting-results supplement (top-3 finishers) — manual for v1
- ⏳ Admin UI (API is in place; UI is a v1.1 task)
