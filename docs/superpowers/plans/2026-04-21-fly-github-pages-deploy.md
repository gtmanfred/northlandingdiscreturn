# Fly.io + GitHub Pages Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the FastAPI backend to Fly.io and the React frontend to GitHub Pages with automatic GitHub Actions deployments on push to `main`.

**Architecture:** Five files are created or modified: the backend Dockerfile is fixed for production, `fly.toml` defines the Fly.io app, two files fix GitHub Pages SPA routing, and two GitHub Actions workflows handle deployment. All secrets are injected at deploy time — no credentials in files.

**Tech Stack:** Fly.io (flyctl), GitHub Actions, GitHub Pages (actions/deploy-pages), Vite static build, Docker.

---

## File Map

| File | Change |
|------|--------|
| `backend/Dockerfile` | Remove `--reload` and `alembic upgrade head` from CMD |
| `fly.toml` | New — Fly.io app config with release_command for migrations |
| `frontend/public/404.html` | New — GitHub Pages SPA routing redirect |
| `frontend/index.html` | Add redirect-decode script before `<script type="module">` |
| `.github/workflows/deploy-backend.yml` | New — deploy to Fly.io on push to main |
| `.github/workflows/deploy-frontend.yml` | New — build and deploy to GitHub Pages on push to main |

---

## Task 1: Fix backend Dockerfile for production

**Files:**
- Modify: `backend/Dockerfile:7`

The current CMD runs Alembic migrations and starts uvicorn with `--reload`. For production: migrations move to Fly's `release_command` (defined in Task 2), and `--reload` must be removed.

- [ ] **Step 1: Make the change**

Replace line 7 of `backend/Dockerfile`:

```dockerfile
FROM docker.io/python:3.12-slim
WORKDIR /srv
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev
COPY . .
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Verify the image builds**

```bash
docker build -f backend/Dockerfile backend/ -t northlanding-backend-test
```

Expected: build completes without error. The image doesn't need to run successfully (no DB available locally) — just confirm it builds.

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile
git commit -m "fix: remove --reload and alembic from Dockerfile CMD for production"
```

---

## Task 2: Create fly.toml

**Files:**
- Create: `fly.toml` (repo root)

- [ ] **Step 1: Create the file**

Create `fly.toml` at the repo root with this exact content:

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

Notes on key settings:
- `primary_region = "ord"` — Chicago. Change to your nearest region if preferred (list: `fly platform regions`).
- `auto_stop_machines = true` with `min_machines_running = 0` — machine sleeps when idle, minimizing cost.
- `release_command = "uv run alembic upgrade head"` — runs inside a temporary container with the new image before traffic shifts. Runs once per deploy, not on every boot.
- `FRONTEND_URL = "https://gtmanfred.github.io"` — used by FastAPI's `CORSMiddleware`. CORS origins are scheme+host only (no path).
- All secrets (`SECRET_KEY`, `DATABASE_URL`, `GOOGLE_CLIENT_ID`, etc.) are set via `fly secrets set`, not in this file.

- [ ] **Step 2: Validate the config (if flyctl is installed)**

```bash
flyctl config validate
```

Expected: `App configuration is valid` or similar. If flyctl is not installed, skip this step — the CI deploy will catch syntax errors.

- [ ] **Step 3: Commit**

```bash
git add fly.toml
git commit -m "feat: add fly.toml for Fly.io deployment"
```

---

## Task 3: Fix GitHub Pages SPA routing

**Files:**
- Create: `frontend/public/404.html`
- Modify: `frontend/index.html:9` (before `<script type="module">`)

GitHub Pages returns a real 404 for deep links like `/northlandingdiscreturn/admin/discs`. The fix: a `404.html` that encodes the intended path as a query param and redirects to `index.html`, plus a decode script in `index.html` that restores the path before React Router boots.

- [ ] **Step 1: Create `frontend/public/404.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>North Landing Disc Return</title>
    <script>
      // Redirect deep links to index.html for SPA routing on GitHub Pages.
      // Encodes the path as a query param: /northlandingdiscreturn/admin/discs
      // becomes /northlandingdiscreturn/?/admin/discs
      var l = window.location;
      l.replace(
        l.protocol + '//' + l.host +
        l.pathname.split('/').slice(0, 2).join('/') + '/?/' +
        l.pathname.slice(1).split('/').slice(1).join('/').replace(/&/g, '~and~') +
        (l.search ? '&' + l.search.slice(1).replace(/&/g, '~and~') : '') +
        l.hash
      );
    </script>
  </head>
  <body></body>
</html>
```

Explanation: `l.pathname.split('/').slice(0, 2).join('/')` keeps the `/northlandingdiscreturn` prefix. Everything after becomes the encoded path appended after `/?/`.

- [ ] **Step 2: Add decode script to `frontend/index.html`**

Replace the current `frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>North Landing Disc Return</title>
    <script>
      // Decode the path encoded by 404.html back into browser history
      // before React Router initializes.
      (function (l) {
        if (l.search[1] === '/') {
          var decoded = l.search
            .slice(1)
            .split('&')
            .map(function (s) { return s.replace(/~and~/g, '&'); })
            .join('?');
          window.history.replaceState(
            null,
            null,
            l.pathname.slice(0, -1) + decoded + l.hash
          );
        }
      }(window.location));
    </script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Verify the file appears in the Vite build output**

```bash
cd frontend && npm run build
ls dist/404.html
```

Expected: `dist/404.html` exists. Files in `frontend/public/` are copied to `dist/` by Vite automatically.

If `npm run build` fails (node_modules not installed): this step can be verified in CI when the deploy-frontend workflow runs.

- [ ] **Step 4: Commit**

```bash
git add frontend/public/404.html frontend/index.html
git commit -m "feat: add GitHub Pages SPA routing fix (404.html redirect + decode script)"
```

---

## Task 4: Create backend deploy workflow

**Files:**
- Create: `.github/workflows/deploy-backend.yml`

- [ ] **Step 1: Create the directory and file**

```bash
mkdir -p .github/workflows
```

Create `.github/workflows/deploy-backend.yml`:

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

Key points:
- `paths:` filter — only triggers when backend code, fly.toml, or the workflow itself changes
- `concurrency: deploy-backend` — prevents two backend deploys running simultaneously
- `--remote-only` — Fly builds the Docker image on their infrastructure; no local Docker daemon needed in CI
- `FLY_API_TOKEN` must be added to GitHub repo secrets before the first deploy (see Manual Setup below)

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-backend.yml'))" && echo "valid"
```

Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-backend.yml
git commit -m "feat: add GitHub Actions workflow to deploy backend to Fly.io"
```

---

## Task 5: Create frontend deploy workflow

**Files:**
- Create: `.github/workflows/deploy-frontend.yml`

- [ ] **Step 1: Create the file**

Create `.github/workflows/deploy-frontend.yml`:

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

      - name: Install dependencies
        run: npm ci
        working-directory: frontend

      - name: Build
        run: npm run build
        working-directory: frontend
        env:
          VITE_API_URL: https://northlandingdiscreturn-api.fly.dev

      - uses: actions/upload-pages-artifact@v3
        with:
          path: frontend/dist

      - uses: actions/deploy-pages@v4
        id: deployment
```

Key points:
- `paths:` filter — only triggers when frontend code or the workflow itself changes
- `permissions: pages: write, id-token: write` — required for GitHub Pages deployment via OIDC (no token needed)
- `cache: 'npm'` with `cache-dependency-path` — caches `node_modules` between runs using `package-lock.json` as the cache key
- `VITE_API_URL` is hardcoded (not a secret) — it's the public backend URL, baked into the JS bundle at build time
- `cancel-in-progress: true` — if two frontend changes land quickly, only the latest deploy finishes

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-frontend.yml'))" && echo "valid"
```

Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-frontend.yml
git commit -m "feat: add GitHub Actions workflow to deploy frontend to GitHub Pages"
```

---

## Manual Setup (one-time, done by developer)

These steps are performed once in the terminal/browser before the first deploy. They are not automated.

**1. Install flyctl and log in**
```bash
brew install flyctl
fly auth login
```

**2. Create the Fly app**

Run from the repo root. When prompted, say **no** to deploying now and **no** to overwriting the `fly.toml` you already created:
```bash
fly launch --no-deploy --name northlandingdiscreturn-api
```

If `fly launch` insists on generating a new `fly.toml`, accept it and then restore the committed version afterwards.

**3. Create and attach Fly Postgres**
```bash
fly postgres create --name northlandingdiscreturn-db --region ord
fly postgres attach northlandingdiscreturn-db
```

`attach` automatically sets `DATABASE_URL` as a Fly secret. Verify with `fly secrets list`.

**4. Create a Supabase project**

Go to [supabase.com](https://supabase.com), create a new project, then from the project dashboard → Settings → API, copy:
- **Project URL** → `SUPABASE_URL`
- **service_role** key → `SUPABASE_SERVICE_KEY`

**5. Set all remaining Fly secrets**
```bash
fly secrets set \
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
  GOOGLE_CLIENT_ID=your-client-id \
  GOOGLE_CLIENT_SECRET=your-client-secret \
  SUPABASE_URL=https://your-project.supabase.co \
  SUPABASE_SERVICE_KEY=your-service-role-key \
  ADMIN_EMAILS=you@example.com
```

Verify all secrets are set:
```bash
fly secrets list
```

Expected: `DATABASE_URL`, `SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ADMIN_EMAILS` all appear.

**6. Update Google OAuth redirect URI**

In [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials → your OAuth 2.0 client:
- Add `https://northlandingdiscreturn-api.fly.dev/auth/callback` to **Authorized redirect URIs**

**7. Enable GitHub Pages**

In the GitHub repo → Settings → Pages → Source: select **GitHub Actions**.

**8. Add `FLY_API_TOKEN` to GitHub secrets**

```bash
fly tokens create deploy -x 999999h
```

Copy the output token. In the GitHub repo → Settings → Secrets and variables → Actions → New repository secret:
- Name: `FLY_API_TOKEN`
- Value: the token from above

**9. First deploy**

Push any change to `main` (or push the commits from Tasks 1–5) to trigger both workflows. Monitor at:
- Backend: `https://github.com/gtmanfred/northlandingdiscreturn/actions`
- Backend logs: `fly logs`
- Frontend: `https://gtmanfred.github.io/northlandingdiscreturn/`
