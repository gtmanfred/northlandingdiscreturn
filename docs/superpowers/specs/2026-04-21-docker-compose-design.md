# Docker Compose Local Dev Design

## Goal

Single `docker compose up` starts the full app stack locally: Postgres, Supabase Storage, FastAPI backend, and Vite frontend.

## Architecture

Four containers, one network:

| Service | Image / Build | Internal Port | Host Port |
|---|---|---|---|
| `db` | `postgres:16` | 5432 | 5432 |
| `storage` | `supabase/storage-api` | 5000 | 5000 |
| `backend` | `./backend/Dockerfile` | 8000 | 8000 |
| `frontend` | `./frontend/Dockerfile` | 5173 | 5173 |

`imgproxy` is excluded — image transformation is disabled (`ENABLE_IMAGE_TRANSFORMATION=false`). Photos are stored and served at original size.

## Service Details

### db

Standard Postgres 16. Hosts both the app schema (users, discs, events) and the Supabase Storage internal schema (`storage.*`). The storage service auto-migrates its own schema on first startup.

### storage

`supabase/storage-api` in filesystem mode — photos land in a Docker volume at `/var/lib/storage`. The Supabase Python client on the backend talks to `http://storage:5000` internally. Authentication uses pre-baked local JWT tokens (a known `JWT_SECRET` + corresponding `anon` and `service_role` JWTs, the same pattern Supabase uses for their own local dev tooling — safe to commit to `.env.example`).

The `disc-photos` bucket is created on backend startup via a lifespan hook that calls the storage API to create the bucket if it does not exist.

### backend

Built from `backend/Dockerfile` (replaces `Dockerfile.j2`). The startup command runs Alembic migrations then starts uvicorn:

```
sh -c "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
```

`--reload` is included for local dev (uvicorn watches for changes via the bind mount).

### frontend

New `frontend/Dockerfile` running the Vite dev server. Polling-based file watching is enabled in `vite.config.ts` (`server.watch.usePolling: true`) to work reliably with Lima bind mounts on macOS. Source is bind-mounted into the container; `node_modules` is kept in an anonymous volume to prevent the host `node_modules` from shadowing the container's.

## Files Created / Modified

| Path | Action |
|---|---|
| `docker-compose.yml` | Create (project root) |
| `backend/Dockerfile` | Create (replaces `Dockerfile.j2`) |
| `frontend/Dockerfile` | Create |
| `.env.example` | Create (project root, consolidated) |
| `.gitignore` | Create (project root, ignores `.env`) |
| `frontend/vite.config.ts` | Modify (add `server.watch.usePolling`) |
| `backend/app/main.py` | Modify (add bucket-creation lifespan hook) |

`backend/Dockerfile.j2` is deleted — it is superseded by the real Dockerfile.

## Environment Variables

Single `.env` at the project root (gitignored). `docker-compose.yml` loads it via `env_file: .env` on each service. `.env.example` is committed and contains:

```
# Required — generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Twilio (leave blank to disable SMS)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# Supabase local dev — pre-baked, safe to commit
SUPABASE_JWT_SECRET=super-secret-jwt-token-with-at-least-32-characters-long
SUPABASE_ANON_KEY=<pre-baked anon JWT>
SUPABASE_SERVICE_KEY=<pre-baked service_role JWT>
```

The pre-baked JWTs are generated once during implementation from the known `SUPABASE_JWT_SECRET` using `python-jose` and committed to `.env.example`.

## Startup Sequence

1. `db` starts, healthcheck passes (`pg_isready`)
2. `storage` starts (depends on `db` healthy) — migrates its schema, creates tables
3. `backend` starts (depends on `db` healthy, `storage` started) — runs `alembic upgrade head`, creates `disc-photos` bucket if missing, starts uvicorn
4. `frontend` starts (depends on `backend` started) — starts Vite dev server

## Developer Workflow

```bash
# First time
cp .env.example .env
# Fill in SECRET_KEY, GOOGLE_*, TWILIO_* in .env

# Start everything
docker compose up

# Rebuild after dependency changes
docker compose build backend   # or frontend
docker compose up

# Stop and remove containers (keep volumes)
docker compose down

# Wipe volumes (reset all data)
docker compose down -v
```

App is available at:
- Frontend: http://localhost:5173
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Storage: http://localhost:5000

## Networking

All services share a single Docker bridge network (`northlanding`). Inter-service communication uses service names as hostnames. The frontend uses `VITE_API_URL=http://localhost:8000` — the browser resolves `localhost` to the host, which maps to the backend container's exposed port. No Vite proxy is needed.

## Known Limitations

- **Google OAuth redirect URIs**: Must include `http://localhost:8000/auth/callback` in the Google Cloud Console for local dev.
- **Twilio**: Test credentials work locally; leave blank to run without SMS.
- **File watching on macOS/Lima**: Polling adds ~1s latency to hot reload. This is expected.
- **Storage persistence**: Photos survive `docker compose down` but are wiped by `docker compose down -v`.
