# North Landing Disc Return

A web application for managing lost disc golf discs at North Landing. Players log found discs with photos; disc owners can log in, add discs to their wishlist, and claim them. Admins manage the full disc inventory, pickup events, and SMS notifications.

**Live app:** https://gtmanfred.github.io/northlandingdiscreturn/  
**API:** https://northlandingdiscreturn-api.fly.dev

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic, uv |
| Database | PostgreSQL 16 |
| Auth | Google OAuth2 + JWT session tokens |
| Storage | Supabase Storage (self-hosted locally, cloud in production) |
| SMS | Twilio (optional) |
| Frontend | React 18, TypeScript, Vite, TanStack Query, Tailwind CSS |
| Backend hosting | Fly.io |
| Frontend hosting | GitHub Pages |
| CI/CD | GitHub Actions |

---

## Local Development

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for frontend-only work outside Docker)
- Python 3.12 + [uv](https://docs.astral.sh/uv/) (for backend-only work outside Docker)

### Setup

**1. Clone the repo**

```bash
git clone git@github.com:gtmanfred/northlandingdiscreturn.git
cd northlandingdiscreturn
```

**2. Configure environment variables**

```bash
cp .env.example .env
```

Edit `.env` and fill in at minimum:

- `SECRET_KEY` — generate one: `python -c "import secrets; print(secrets.token_hex(32))"`
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — from [Google Cloud Console](https://console.cloud.google.com). Add `http://localhost:8000/auth/callback` as an authorized redirect URI.
- `ADMIN_EMAILS` — comma-separated list of emails that should have admin access.

All other values have working defaults for local development. Supabase keys in `.env.example` are pre-baked local dev tokens and are safe to use as-is.

**3. Start the stack**

```bash
docker compose up
```

This starts:

| Service | URL |
|---------|-----|
| Frontend (Vite dev server) | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| PostgreSQL | localhost:5432 |
| Supabase Storage | localhost:5000 |

The backend runs `alembic upgrade head` automatically before starting, so the database schema is always up to date.

**4. API docs**

FastAPI's interactive docs are available at http://localhost:8000/docs.

---

## Environment Variables

### Root `.env` (Docker Compose)

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Random secret for JWT signing. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `POSTGRES_PASSWORD` | No | Postgres password. Defaults to `secret`. |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth client ID. |
| `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth client secret. |
| `ADMIN_EMAILS` | No | Comma-separated emails promoted to admin on startup. |
| `TWILIO_ACCOUNT_SID` | No | Leave blank to disable SMS notifications. |
| `TWILIO_AUTH_TOKEN` | No | Leave blank to disable SMS notifications. |
| `TWILIO_FROM_NUMBER` | No | Leave blank to disable SMS notifications. |
| `SUPABASE_JWT_SECRET` | No | Pre-baked local dev value in `.env.example`. |
| `SUPABASE_ANON_KEY` | No | Pre-baked local dev JWT in `.env.example`. |
| `SUPABASE_SERVICE_KEY` | No | Pre-baked local dev JWT in `.env.example`. |

### Backend-only config (`backend/app/config.py`)

These are set automatically by Docker Compose. For standalone backend dev, set them manually:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/northlanding` | Async PostgreSQL URL. |
| `FRONTEND_URL` | `http://localhost:5173` | Used for auth redirect and CORS origin. |
| `SUPABASE_URL` | `""` | Supabase project URL or local storage URL. |
| `SUPABASE_BUCKET` | `disc-photos` | Storage bucket name. |
| `JWT_EXPIRE_MINUTES` | `60` | Token expiry in minutes. |

---

## Running Tests

Tests use [`teststack`](https://github.com/gtmanfred/teststack) to spin up a throwaway Postgres container:

```bash
cd backend
teststack run tests
```

To run a specific test or pass pytest flags:

```bash
teststack run tests -- -k test_create_disc -v
```

---

## Database Migrations

Migrations live in `backend/alembic/versions/`. Run from the `backend/` directory:

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Generate a new migration from model changes
uv run alembic revision --autogenerate -m "describe the change"

# Roll back one migration
uv run alembic downgrade -1
```

In production (Fly.io), migrations run automatically as part of each deploy via the `release_command` in `fly.toml`.

---

## Frontend Development

The frontend API client (`frontend/src/api/northlanding.ts`) is generated from the OpenAPI schema. To regenerate after backend changes:

```bash
cd frontend
npm run generate:all   # re-exports schema from FastAPI, then regenerates the client
```

Or in two steps:

```bash
npm run generate:schema   # exports openapi.json from FastAPI
npm run generate          # regenerates northlanding.ts from openapi.json
```

Other frontend commands:

```bash
npm run dev      # Vite dev server on :5173
npm run build    # TypeScript check + production build → dist/
npm run preview  # Preview the production build locally
npm run lint     # ESLint
```

---

## Deployment

### Architecture

- **Backend** deploys to [Fly.io](https://fly.io) as a Docker container (app: `northlandingdiscreturn-api`, region: Chicago `ord`).
- **Frontend** deploys to GitHub Pages as a static Vite build at `https://gtmanfred.github.io/northlandingdiscreturn/`.
- Both deploy automatically via GitHub Actions on push to `main`.

### GitHub Actions Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `deploy-backend.yml` | Push to `main` touching `backend/**` or `fly.toml` | `flyctl deploy --remote-only` |
| `deploy-frontend.yml` | Push to `main` touching `frontend/**` | `npm ci && npm run build`, then deploys `dist/` to GitHub Pages |

### One-Time Production Setup

These steps are done once before the first deploy.

**1. Install flyctl and log in**

```bash
brew install flyctl
fly auth login
```

**2. Create the Fly app**

Run from the repo root. When prompted, say **no** to deploying now and **no** to overwriting `fly.toml`:

```bash
fly launch --no-deploy --name northlandingdiscreturn-api
```

**3. Create and attach Fly Postgres**

```bash
fly postgres create --name northlandingdiscreturn-db --region ord
fly postgres attach northlandingdiscreturn-db
```

`attach` automatically sets `DATABASE_URL` as a Fly secret.

**4. Create a Supabase project**

Go to [supabase.com](https://supabase.com), create a project, then from Settings → API copy:
- **Project URL** → `SUPABASE_URL`
- **service_role key** → `SUPABASE_SERVICE_KEY`

**5. Set remaining Fly secrets**

```bash
fly secrets set \
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
  GOOGLE_CLIENT_ID=your-client-id \
  GOOGLE_CLIENT_SECRET=your-client-secret \
  SUPABASE_URL=https://your-project.supabase.co \
  SUPABASE_SERVICE_KEY=your-service-role-key \
  ADMIN_EMAILS=you@example.com
```

Verify all secrets are present:

```bash
fly secrets list
```

Expected: `DATABASE_URL`, `SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ADMIN_EMAILS`.

**6. Update Google OAuth redirect URI**

In [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials → your OAuth client, add:

```
https://northlandingdiscreturn-api.fly.dev/auth/callback
```

**7. Enable GitHub Pages**

In the GitHub repo → Settings → Pages → Source: select **GitHub Actions**.

**8. Add `FLY_API_TOKEN` to GitHub secrets**

```bash
fly tokens create deploy -x 999999h
```

Copy the token. In the GitHub repo → Settings → Secrets and variables → Actions → New repository secret:

- **Name:** `FLY_API_TOKEN`
- **Value:** the token from above

**9. Deploy**

Push any change to `main` to trigger both workflows, or trigger them manually from the Actions tab. Monitor:

```bash
fly logs                          # backend logs
fly status                        # deployment status
```

Frontend: https://gtmanfred.github.io/northlandingdiscreturn/

---

## Project Structure

```
northlandingdiscreturn/
├── backend/
│   ├── app/
│   │   ├── routers/         # auth, discs, users, admin, webhooks, suggestions
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── repositories/    # database query layer
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── services/        # storage, auth helpers
│   │   ├── config.py        # environment configuration (figenv)
│   │   ├── database.py      # async SQLAlchemy engine/session
│   │   └── main.py          # FastAPI app factory
│   ├── alembic/             # migration scripts
│   ├── tests/               # pytest test suite
│   ├── Dockerfile
│   ├── fly.toml
│   ├── pyproject.toml
│   └── teststack.toml
├── frontend/
│   ├── src/
│   │   ├── api/             # orval-generated API client (northlanding.ts)
│   │   ├── components/      # shared UI components
│   │   └── pages/           # LoginPage, MyDiscsPage, MyWishlistPage, Admin*, etc.
│   ├── public/
│   │   └── 404.html         # GitHub Pages SPA routing redirect
│   ├── index.html           # SPA entry point with path decode script
│   └── vite.config.ts
├── .github/
│   └── workflows/
│       ├── deploy-backend.yml
│       └── deploy-frontend.yml
├── docker-compose.yml
└── .env.example
```
