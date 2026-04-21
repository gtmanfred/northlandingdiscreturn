# Fly.io + GitHub Pages Deployment — Design

**Goal:** Deploy the FastAPI backend to Fly.io and the React frontend to GitHub Pages, with automatic GitHub Actions deployments on push to `main`.

**Architecture:** Backend runs on a single Fly.io machine (auto-stop when idle) backed by Fly managed Postgres and cloud Supabase for photo storage. Frontend is a static Vite build deployed to GitHub Pages. Two independent GitHub Actions workflows handle deployment — backend triggers on changes under `backend/` or `fly.toml`, frontend triggers on changes under `frontend/`.

**Tech Stack:** Fly.io (flyctl, fly.toml), GitHub Actions, GitHub Pages, Supabase cloud (photo storage), Vite static build.

---

## Backend — Fly.io

### `fly.toml` (new, at repo root)

```toml
app = "northlandingdiscreturn-api"
primary_region = "ord"

[build]
  dockerfile = "backend/Dockerfile"

[deploy]
  release_command = "uv run alembic upgrade head"

[env]
  SUPABASE_BUCKET = "disc-photos"
  FRONTEND_URL = "https://gtmanfred.github.io"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0
  processes = ["app"]

[[vm]]
  memory = "256mb"
  cpu_kind = "shared"
  cpus = 1
```

Key decisions:
- `auto_stop_machines = true` / `min_machines_running = 0` — machine sleeps when idle to minimize cost
- `release_command` runs Alembic migrations once before each new version goes live — not in CMD
- `FRONTEND_URL = "https://gtmanfred.github.io"` — used by FastAPI's `CORSMiddleware` as the allowed origin (CORS origins are scheme+host, no path)
- Non-secret config inlined under `[env]`; all secrets set via `fly secrets set`

### `backend/Dockerfile` changes

Two production fixes to the CMD:
- Remove `--reload` — live-reload is for development only
- Remove `alembic upgrade head` — migrations now run as Fly's `release_command`

```dockerfile
FROM docker.io/python:3.12-slim
WORKDIR /srv
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev
COPY . .
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Fly secrets (set once, not in files)

Set via `fly secrets set KEY=value ...` after `fly launch`:

| Secret | Source |
|--------|--------|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Auto-injected when running `fly postgres attach` |
| `GOOGLE_CLIENT_ID` | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console |
| `SUPABASE_URL` | Supabase project settings → API → Project URL |
| `SUPABASE_SERVICE_KEY` | Supabase project settings → API → service_role key |
| `ADMIN_EMAILS` | Comma-separated list of admin emails |
| `TWILIO_ACCOUNT_SID` | Optional — leave unset to disable SMS |
| `TWILIO_AUTH_TOKEN` | Optional |
| `TWILIO_FROM_NUMBER` | Optional |

`SUPABASE_JWT_SECRET` and `SUPABASE_ANON_KEY` are not needed — those are only consumed by the self-hosted Supabase Storage container, which is replaced by cloud Supabase in production.

---

## Frontend — GitHub Pages

### SPA routing fix

GitHub Pages returns a 404 for any URL that isn't a real file (e.g., `/northlandingdiscreturn/admin/discs` on hard refresh). The fix:

1. **`frontend/public/404.html`** — intercepts 404s and redirects to `index.html` with the intended path encoded as a query param
2. **`frontend/index.html`** — adds a one-time script that decodes the query param back into the browser history before React Router boots

This is the canonical GitHub Pages SPA workaround (no build-tool changes required).

### `VITE_API_URL`

Hardcoded in the GitHub Actions workflow as `https://northlandingdiscreturn-api.fly.dev` — not a secret since it's a public endpoint. At build time Vite bakes this into the JS bundle.

---

## GitHub Actions Workflows

### `.github/workflows/deploy-backend.yml`

```yaml
name: Deploy backend to Fly.io

on:
  push:
    branches: [main]
    paths:
      - 'backend/**'
      - 'fly.toml'
      - '.github/workflows/deploy-backend.yml'

jobs:
  deploy:
    name: Deploy
    runs-on: ubuntu-latest
    concurrency: deploy-backend
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

`--remote-only` means Fly builds the Docker image on their builders — no Docker daemon needed in CI.

### `.github/workflows/deploy-frontend.yml`

```yaml
name: Deploy frontend to GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - 'frontend/**'
      - '.github/workflows/deploy-frontend.yml'

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    name: Deploy
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
        working-directory: frontend
      - run: npm run build
        working-directory: frontend
        env:
          VITE_API_URL: https://northlandingdiscreturn-api.fly.dev
      - uses: actions/upload-pages-artifact@v3
        with:
          path: frontend/dist
      - uses: actions/deploy-pages@v4
        id: deployment
```

---

## One-Time Setup Checklist

These are manual steps done once by the developer before the first deploy:

1. **Install flyctl** — `brew install flyctl && fly auth login`
2. **Create Fly app** — `fly launch --no-deploy` from repo root (generates initial `fly.toml`, which will be replaced by the one above)
3. **Create Fly Postgres** — `fly postgres create --name northlandingdiscreturn-db` then `fly postgres attach northlandingdiscreturn-db` (auto-sets `DATABASE_URL` secret)
4. **Set Fly secrets** — `fly secrets set SECRET_KEY=... GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... SUPABASE_URL=... SUPABASE_SERVICE_KEY=... ADMIN_EMAILS=...`
5. **Create Supabase project** — at supabase.com, create a new project; copy the Project URL and `service_role` key for step 4
6. **Update Google OAuth** — add `https://northlandingdiscreturn-api.fly.dev/auth/callback` as an authorized redirect URI in Google Cloud Console
7. **Enable GitHub Pages** — in repo Settings → Pages → Source: GitHub Actions
8. **Add GitHub secret** — `FLY_API_TOKEN`: generate with `fly tokens create deploy -x 999999h`, add to repo Settings → Secrets → Actions
9. **First deploy** — push to `main` or trigger workflows manually

---

## What Is Not Included

- **SMS worker** — `backend/worker/main.py` is not deployed; Twilio secrets are optional and the app degrades gracefully without them
- **Self-hosted Supabase Storage** — replaced entirely by cloud Supabase; the `docker/init-storage-schema.sql` and compose storage service are dev-only
- **Staging environment** — single production environment only
