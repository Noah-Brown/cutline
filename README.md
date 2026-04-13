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

## Deploying to an Ubuntu server

The included `docker-compose.yml` runs the full stack — Postgres, FastAPI
backend, Next.js frontend, and Caddy as a reverse proxy with **automatic
HTTPS** via Let's Encrypt.

### One-time host setup

```bash
# Install Docker Engine + the compose plugin (Ubuntu 22.04 / 24.04)
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Open the web ports (skip if you already use ufw / a cloud firewall)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### Configure and launch

```bash
# 1. Clone the repo
git clone https://github.com/Noah-Brown/cutline.git
cd cutline

# 2. Configure
cp .env.example .env
$EDITOR .env
#   • Set CUTLINE_DOMAIN to your DNS name (skip for HTTP-only on port 80).
#   • Set ADMIN_TOKEN to a random secret (e.g. `openssl rand -hex 32`).
#   • Set POSTGRES_PASSWORD to something strong.

# 3. Build + start everything (postgres → migrate → backend → frontend → caddy)
sudo docker compose up -d --build

# 4. Seed today's sample puzzle (optional, for first-day demo)
sudo docker compose exec backend python -m scripts.seed_sample
```

That's it. Visit your domain (or `http://<server-ip>` if no DNS) to play.

### Operating

```bash
# Tail logs
sudo docker compose logs -f backend
sudo docker compose logs -f caddy

# Restart a single service after an env change
sudo docker compose up -d backend

# Rebuild the frontend after changing NEXT_PUBLIC_API_BASE
sudo docker compose build frontend && sudo docker compose up -d frontend

# Open a Postgres shell
sudo docker compose exec postgres psql -U cutline -d cutline
```

### Loading Lahman data on the server

The host's `./data/` directory is mounted read-only into the backend container
at `/data/lahman`. To ingest:

```bash
# Copy the zip up to the server (from your laptop)
scp baseballdatabank-2024.zip user@server:/path/to/cutline/data/

# Run the ingest inside the running backend container
sudo docker compose exec backend \
  python -m scripts.ingest_lahman --zip /data/lahman/baseballdatabank-2024.zip
```

### TLS / DNS notes

When `CUTLINE_DOMAIN` is set to a real DNS name and the domain resolves to
this server, Caddy automatically requests and renews a Let's Encrypt
certificate. Certs are persisted in the `caddy_data` volume across restarts.

Common gotchas:
- The DNS A record must be live **before** the first `docker compose up`,
  otherwise Caddy's ACME challenge fails. Rate limits apply.
- If you change `CUTLINE_DOMAIN`, run `docker compose up -d caddy` to pick
  it up.
- Behind another reverse proxy (Cloudflare proxied DNS, AWS ALB)? Disable
  Caddy's auto-TLS by setting `CUTLINE_DOMAIN=:80` and let the upstream
  handle TLS.

### Persistent state

| Volume         | Contents                                 |
| -------------- | ---------------------------------------- |
| `pgdata`       | Postgres database files                  |
| `photos`       | Uploaded player headshots                 |
| `caddy_data`   | TLS certs and Caddy state                |
| `caddy_config` | Caddy admin API config                   |

Back these up with `docker run --rm -v <volume>:/v -v $PWD:/backup alpine tar czf /backup/<name>.tgz -C /v .`.

### Local dev with the same compose stack

For a smoke test on your laptop, the defaults give you HTTP-only on
`http://localhost`:

```bash
cp .env.example .env   # leave CUTLINE_DOMAIN commented out
docker compose up --build
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
| POST   | `/api/admin/puzzle`                    | Create/schedule a puzzle                    |
| GET    | `/api/admin/puzzle/preview`            | Preview a puzzle before publishing          |
| GET    | `/api/admin/categories`                | List registered category types              |
| GET    | `/api/admin/players/search`            | Search players for puzzle building          |
| PATCH  | `/api/admin/players/{id}`              | Update a player (currently just `photo_url`) |
| POST   | `/api/admin/players/{id}/photo`        | Upload a headshot (multipart; JPEG/PNG/WebP) |

## Player photos (manual)

Players can have an optional headshot. There are two ways to attach one via
the admin API:

```bash
# 1. Upload a file (persisted under backend/uploads/photos/<player_id>.<ext>)
curl -X POST http://localhost:8000/api/admin/players/42/photo \
  -H "Authorization: Bearer dev-admin-token" \
  -F file=@headshot.png

# 2. Or paste an external URL (e.g. Wikimedia Commons)
curl -X PATCH http://localhost:8000/api/admin/players/42 \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"photo_url":"https://upload.wikimedia.org/.../Barry_Bonds_2007.jpg"}'
```

Uploaded files are served from `/photos/<id>.<ext>`. The frontend resolves
relative paths against the API base and falls back to an initials circle
when a photo is missing or fails to load. Accepted types: JPEG, PNG, WebP.
Max size: 5 MB (configurable via `PHOTO_MAX_BYTES`).

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
