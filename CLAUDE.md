# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Cutline is a daily MLB grid trivia game. One category, a 3×3 grid of 9 player names, a mix of real qualifiers and "imposter" near-misses. Players mark each card YES / NO / blank; +1 correct, −1 wrong, 0 blank. Max score 9.

## Commands

### Backend (FastAPI, Python 3.11+)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# Default DATABASE_URL is sqlite+aiosqlite:///./cutline.db. Postgres works too:
export DATABASE_URL=postgresql+asyncpg://cutline:cutline@localhost:5432/cutline

alembic upgrade head                  # apply migrations
python -m scripts.seed_sample         # insert hand-curated sample puzzle
uvicorn app.main:app --reload         # serves :8000, /docs for OpenAPI

pytest                                # run all tests
pytest tests/test_scoring.py          # a single file
pytest tests/test_api.py::test_name   # a single test
ruff check .                          # lint
```

Alembic migrations live in `backend/alembic/`. Create a new one via `alembic revision --autogenerate -m "…"` then `alembic upgrade head`. `DATABASE_URL` must include an async driver prefix (`postgresql+asyncpg://` or `sqlite+aiosqlite://`).

### Frontend (Next.js 14 App Router, TypeScript, Tailwind)
```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev   # :3000
npm run build
npm run lint
npm run typecheck                                         # tsc --noEmit
```

`NEXT_PUBLIC_API_BASE` is baked in at build time. Leave empty to use relative `/api/...` paths through a reverse proxy (Caddy in prod).

### Data ingestion
Lahman-formatted CSVs (Chadwick Bureau Baseball Databank) load via `python -m scripts.ingest_lahman --path <dir>` or `--zip <file.zip>`. Winners come from `AwardsPlayers.csv`; non-winning vote recipients from `AwardsSharePlayers.csv` / `AwardsShareManagers.csv` are tagged in `Award.notes` as `top_3` (≥40% share) or `top_5`, feeding the imposter pool for award categories.

### Automated puzzle generation
`python -m scripts.generate_puzzles --days 7` produces published puzzles for the next 7 dates, skipping any date that already has one. Flags: `--date YYYY-MM-DD` for a single day, `--start YYYY-MM-DD --days N` for a range, `--dry-run` to preview. Generator logic lives in `app/puzzle_generator.py` — date-seeded weighted sampling over All-Star-gated pools, with a 14-day category rotation window and refuse-to-publish guardrails if pools are too thin.

### Docker Compose (full stack)
`docker compose up -d --build` brings up postgres → migrate (one-shot) → backend → frontend → caddy. Configure via `.env` (see `.env.example`; `CUTLINE_DOMAIN` enables Let's Encrypt automatic TLS). Seed after first start with `docker compose exec backend python -m scripts.seed_sample`.

## Architecture

### Backend layout (`backend/app/`)
- `main.py` — `create_app()` wires CORS, puzzle + admin routers, mounts `/photos` StaticFiles over `photo_upload_dir`.
- `config.py` — pydantic-settings; all env vars resolved via `get_settings()` (cached).
- `database.py` — single async engine + `async_sessionmaker`; `get_session()` FastAPI dep yields a request-scoped `AsyncSession`.
- `models.py` — ORM: `Player`, `Award`, `SeasonStat`, `AllStarAppearance`, `PlayerTeam`, `Puzzle`, `PuzzleEntry`, `Submission`. `Submission.selections` is JSON (stores `{"yes": [...], "no": [...]}`) for SQLite compatibility — don't assume Postgres ARRAY.
- `scoring.py` — tri-state `Mark` (YES/NO/BLANK) → `ResultKind` → points via `_POINTS`. `score_submission()` is pure; `render_share_text()` builds the spoiler-free share string with emoji grid.
- `categories.py` — `REGISTRY: dict[str, Category]` maps `category_type` keys (e.g. `award_mvp_nl`) to async `qualifier_fn` / `imposter_fn` callables. This is where puzzle-building category logic lives; award types are pre-registered, stat/intersection categories extend the same interface.
- `routers/puzzle.py` — public: `/api/puzzle/today|submit|stats|streak|{date}`. Today falls back to most-recent published puzzle if no puzzle matches today's ET date. Submit enforces one submission per `(puzzle_id, session_id)` via unique constraint + 409.
- `routers/admin.py` — admin CRUD, category listing, qualifier-pool endpoint, player search, player patch, photo upload. Auth = bearer `ADMIN_TOKEN` header. `get_photo_dir` is a FastAPI dep so tests can override.
- `schemas.py` — pydantic request/response shapes.

### Frontend layout (`frontend/`)
- `app/page.tsx` — the entire game UI: fetches today, persists tri-state marks + results in `localStorage` via `lib/session.ts`, submits once, then shows `Reveal`.
- `lib/api.ts` — typed fetch wrappers + `resolvePhotoUrl` (resolves relative photo URLs against `API_BASE`, or returns absolute URLs as-is).
- `lib/session.ts` — persistent session ID + per-date marks/results cache (localStorage).
- `lib/stats.ts` — client-side streak/distribution tracking.
- `components/` — `Grid`, `Card`, `Header`, `Reveal`, `ShareButton`, `Stats`.

### Key conventions & invariants
- **Date handling** — puzzles roll over at midnight US Central; `_today_local()` in `routers/puzzle.py` uses `zoneinfo("America/Chicago")` and the frontend `timeUntilNextPuzzle` mirrors that via `Intl` on `America/Chicago`. DST-safe on both sides.
- **Scoring is tri-state**, not boolean. Submissions send `{yes: [...], no: [...]}`; unlisted positions are blank. Scoring is mirrored: YES on qualifier and NO on imposter both score +1.
- **One puzzle per date.** `puzzles.puzzle_date` is UNIQUE; admin puzzle create returns 409 on conflict.
- **One submission per (puzzle, session).** Session IDs are generated client-side and stored in localStorage.
- **Photo URLs** can be absolute (external) or relative (`/photos/<id>.<ext>` served from the upload dir). Frontend resolves via `resolvePhotoUrl`.
- **Tests use a file-backed SQLite DB** (`./_cutline_test.db`) because in-memory async SQLite is flaky — see `tests/conftest.py`. Each test drops+creates all tables. The `client` fixture overrides `get_session` and `get_photo_dir`.
- **Category registry is the extension point** for new puzzle types; add a `Category` to `REGISTRY` rather than branching in routers.
