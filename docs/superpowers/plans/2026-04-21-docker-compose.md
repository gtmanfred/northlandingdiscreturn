# Docker Compose Local Dev Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up a single `docker compose up` that starts Postgres, Supabase Storage, the FastAPI backend, and the Vite frontend for fully local development.

**Architecture:** Four containers on one bridge network. Supabase Storage runs in filesystem mode (no S3, no imgproxy). Backend bind-mounts source with a separate named volume for the virtualenv so `uv sync`'d packages survive. Frontend bind-mounts source with an anonymous volume protecting `node_modules`.

**Tech Stack:** Docker Compose v2, Python 3.12 / uv, Node 20 / npm, supabase/storage-api, postgres:16, FastAPI/uvicorn --reload, Vite dev server

---

## File Map

| Path | Action |
|---|---|
| `docker-compose.yml` | Create (project root) |
| `backend/Dockerfile` | Create |
| `backend/Dockerfile.j2` | Delete |
| `frontend/Dockerfile` | Create |
| `.env.example` | Create (project root) |
| `.gitignore` | Create (project root) |
| `frontend/vite.config.ts` | Modify — add `server.host` + `server.watch.usePolling` |
| `backend/app/main.py` | Modify — add `_ensure_storage_bucket` + lifespan |
| `backend/tests/test_lifespan.py` | Create |

---

### Task 1: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`
- Delete: `backend/Dockerfile.j2`

- [ ] **Step 1: Create `backend/Dockerfile`**

```dockerfile
FROM docker.io/python:3.12-slim
WORKDIR /srv
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync
COPY . .
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
```

- [ ] **Step 2: Delete `backend/Dockerfile.j2`**

```bash
git rm backend/Dockerfile.j2
```

- [ ] **Step 3: Verify the image builds**

```bash
docker build -t northlanding-backend ./backend
```

Expected: build completes without error. The final layer should show `CMD`.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile
git commit -m "feat: add backend Dockerfile, remove Dockerfile.j2 template"
```

---

### Task 2: Frontend Dockerfile and Vite polling

**Files:**
- Create: `frontend/Dockerfile`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Add `server` config to `frontend/vite.config.ts`**

Replace the entire file with:

```ts
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/northlandingdiscreturn/' : '/',
  server: {
    host: true,
    watch: {
      usePolling: true,
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
}))
```

`host: true` binds Vite to `0.0.0.0` so the container port is reachable. `usePolling: true` enables inotify-free file watching needed for Lima bind mounts on macOS.

- [ ] **Step 2: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]
```

- [ ] **Step 3: Verify the image builds**

```bash
docker build -t northlanding-frontend ./frontend
```

Expected: build completes, `npm install` succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/Dockerfile frontend/vite.config.ts
git commit -m "feat: add frontend Dockerfile, enable Vite host+polling for Docker"
```

---

### Task 3: Bucket creation lifespan hook

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_lifespan.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lifespan.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from app.main import _ensure_storage_bucket


@pytest.mark.asyncio
async def test_skips_when_no_supabase_config():
    with patch("app.main.get_storage_client") as mock_get:
        await _ensure_storage_bucket()
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_creates_disc_photos_bucket(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://storage:5000")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    mock_client = MagicMock()
    with patch("app.main.get_storage_client", return_value=mock_client):
        await _ensure_storage_bucket()
    mock_client.storage.create_bucket.assert_called_once_with(
        "disc-photos", options={"public": True}
    )


@pytest.mark.asyncio
async def test_ignores_bucket_already_exists_error(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://storage:5000")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    mock_client = MagicMock()
    mock_client.storage.create_bucket.side_effect = Exception("Bucket already exists")
    with patch("app.main.get_storage_client", return_value=mock_client):
        await _ensure_storage_bucket()  # must not raise
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_lifespan.py -v
```

Expected: `ImportError: cannot import name '_ensure_storage_bucket' from 'app.main'`

- [ ] **Step 3: Implement `_ensure_storage_bucket` and lifespan in `backend/app/main.py`**

Replace the entire file with:

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.routers import auth, discs, users, admin, webhooks
from app.services.storage import get_storage_client


async def _ensure_storage_bucket() -> None:
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        return

    def _create():
        client = get_storage_client()
        try:
            client.storage.create_bucket(settings.SUPABASE_BUCKET, options={"public": True})
        except Exception:
            pass

    await asyncio.to_thread(_create)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _ensure_storage_bucket()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="North Landing Disc Return", version="0.1.0", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(discs.router, prefix="/discs", tags=["discs"])
    app.include_router(users.router, prefix="/users", tags=["users"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && uv run pytest tests/test_lifespan.py -v
```

Expected:
```
PASSED tests/test_lifespan.py::test_skips_when_no_supabase_config
PASSED tests/test_lifespan.py::test_creates_disc_photos_bucket
PASSED tests/test_lifespan.py::test_ignores_bucket_already_exists_error
3 passed
```

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
cd backend && uv run pytest -v
```

Expected: all previously passing tests still pass (the new lifespan skips bucket creation because SUPABASE_URL is not set in test env).

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_lifespan.py
git commit -m "feat: add storage bucket creation on app startup"
```

---

### Task 4: Root .env.example and .gitignore

**Files:**
- Create: `.env.example` (project root)
- Create: `.gitignore` (project root)

- [ ] **Step 1: Generate the local dev JWT tokens**

Run from the project root (python-jose is already in backend deps):

```bash
cd backend && uv run python -c "
from jose import jwt
import time
SECRET = 'super-secret-jwt-token-with-at-least-32-characters-long'
now = int(time.time())
exp = now + 10 * 365 * 24 * 3600
anon = jwt.encode({'role': 'anon', 'iss': 'supabase-local', 'iat': now, 'exp': exp}, SECRET, algorithm='HS256')
svc = jwt.encode({'role': 'service_role', 'iss': 'supabase-local', 'iat': now, 'exp': exp}, SECRET, algorithm='HS256')
print('SUPABASE_ANON_KEY=' + anon)
print('SUPABASE_SERVICE_KEY=' + svc)
"
```

Copy the two printed values. You will paste them as the values in `.env.example` below.

- [ ] **Step 2: Create `.env.example` at the project root**

Fill in `<anon-jwt>` and `<service-jwt>` with the values printed by Step 1:

```
# Required — generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=

# Google OAuth — register at https://console.cloud.google.com
# Authorized redirect URI for local dev: http://localhost:8000/auth/callback
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Twilio — leave blank to disable SMS notifications
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# Supabase local dev — pre-baked tokens safe to commit
# JWT_SECRET must be at least 32 chars; ANON/SERVICE keys are JWTs signed with it
SUPABASE_JWT_SECRET=super-secret-jwt-token-with-at-least-32-characters-long
SUPABASE_ANON_KEY=<anon-jwt>
SUPABASE_SERVICE_KEY=<service-jwt>
```

- [ ] **Step 3: Create `.gitignore` at the project root**

```
.env
```

- [ ] **Step 4: Verify `.env` is gitignored**

```bash
cp .env.example .env
git status
```

Expected: `.env` does NOT appear in the output (it is ignored). `.env.example` and `.gitignore` appear as new files.

- [ ] **Step 5: Commit**

```bash
git add .env.example .gitignore
git commit -m "feat: add root .env.example with local dev JWT tokens and .gitignore"
```

---

### Task 5: docker-compose.yml and smoke test

**Files:**
- Create: `docker-compose.yml` (project root)

- [ ] **Step 1: Create `docker-compose.yml` at the project root**

```yaml
name: northlanding

services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: northlanding
      POSTGRES_USER: northlanding
      POSTGRES_PASSWORD: secret
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U northlanding -d northlanding"]
      interval: 5s
      timeout: 5s
      retries: 10
    ports:
      - "5432:5432"

  storage:
    image: supabase/storage-api:v0.43.11
    environment:
      ANON_KEY: ${SUPABASE_ANON_KEY}
      SERVICE_KEY: ${SUPABASE_SERVICE_KEY}
      PGRST_JWT_SECRET: ${SUPABASE_JWT_SECRET}
      AUTH_JWT_SECRET: ${SUPABASE_JWT_SECRET}
      DATABASE_URL: postgres://northlanding:secret@db:5432/northlanding
      FILE_SIZE_LIMIT: "52428800"
      STORAGE_BACKEND: file
      FILE_STORAGE_BACKEND_PATH: /var/lib/storage
      TENANT_ID: stub
      REGION: stub
      GLOBAL_S3_BUCKET: stub
      ENABLE_IMAGE_TRANSFORMATION: "false"
    volumes:
      - storage_data:/var/lib/storage
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "5000:5000"

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://northlanding:secret@db:5432/northlanding
      SECRET_KEY: ${SECRET_KEY}
      GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID:-}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET:-}
      TWILIO_ACCOUNT_SID: ${TWILIO_ACCOUNT_SID:-}
      TWILIO_AUTH_TOKEN: ${TWILIO_AUTH_TOKEN:-}
      TWILIO_FROM_NUMBER: ${TWILIO_FROM_NUMBER:-}
      SUPABASE_URL: http://storage:5000
      SUPABASE_SERVICE_KEY: ${SUPABASE_SERVICE_KEY}
      SUPABASE_BUCKET: disc-photos
      FRONTEND_URL: http://localhost:5173
    volumes:
      - ./backend:/srv
      - backend_venv:/srv/.venv
    depends_on:
      db:
        condition: service_healthy
      storage:
        condition: service_started
    ports:
      - "8000:8000"

  frontend:
    build: ./frontend
    environment:
      VITE_API_URL: http://localhost:8000
    volumes:
      - ./frontend:/app
      - /app/node_modules
    depends_on:
      - backend
    ports:
      - "5173:5173"

volumes:
  pg_data:
  storage_data:
  backend_venv:
```

- [ ] **Step 2: Validate the compose file syntax**

```bash
docker compose config
```

Expected: YAML is printed back with no errors.

- [ ] **Step 3: Make sure `.env` exists and has `SECRET_KEY` set**

```bash
grep -q "^SECRET_KEY=." .env || echo "ERROR: SECRET_KEY is empty in .env"
```

If empty, generate one:
```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

- [ ] **Step 4: Start the full stack**

```bash
docker compose up --build
```

If Docker fails to pull `supabase/storage-api:v0.43.11` with "manifest unknown", check the available tags at https://hub.docker.com/r/supabase/storage-api/tags and update the version in `docker-compose.yml` to the latest stable tag.

Wait for all four services to be running. You should see:

- `db` logs: `database system is ready to accept connections`
- `storage` logs: `Server started`
- `backend` logs: `INFO:     Application startup complete.`
- `frontend` logs: `VITE v5.x  ready in ...ms` and `➜  Local:   http://localhost:5173/`

- [ ] **Step 5: Verify the backend health endpoint**

In a new terminal:

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 6: Verify the frontend is reachable**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/
```

Expected: `200`

- [ ] **Step 7: Verify Supabase Storage is reachable from the backend**

```bash
curl http://localhost:5000/status
```

Expected: `{"name":"storage-api","version":"...","date":"..."}` (any JSON response, not a connection error)

- [ ] **Step 8: Stop the stack**

```bash
docker compose down
```

- [ ] **Step 9: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose.yml for full local dev stack"
```
