# Seed Admins via ADMIN_EMAILS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read a comma-separated `ADMIN_EMAILS` env var, promote matching users to admin on startup and at login, and prevent the API from demoting those seed admins.

**Architecture:** `ADMIN_EMAILS` is parsed from a CSV env var using a figenv coerce class into a `list[str]`. The lifespan function gets a new `_promote_seed_admins(db)` helper that runs after storage bucket setup. The OAuth callback gets a `_maybe_promote_to_admin` helper called after every login. The existing `PATCH /admin/users/{user_id}` endpoint rejects demotion of seed admin emails.

**Tech Stack:** FastAPI, figenv (MetaConfig + `_coerce` pattern), SQLAlchemy async (`AsyncSessionLocal`, `User.email.in_(...)`), pytest-asyncio (asyncio_mode=auto), teststack.

---

## File Map

| File | Change |
|------|--------|
| `app/config.py` | Add `csv` coerce class; add `ADMIN_EMAILS: csv = ""` field |
| `app/repositories/user.py` | Add `get_by_emails(emails: list[str]) -> list[User]` |
| `app/main.py` | Add `_promote_seed_admins(db)`; wire into `lifespan`; import `AsyncSessionLocal` |
| `app/routers/auth.py` | Add `_maybe_promote_to_admin` helper; call it in `auth_google_callback` |
| `app/routers/admin.py` | Add demotion guard in `update_user`; import `settings` |
| `tests/test_config.py` | New file — tests for csv coerce |
| `tests/test_lifespan.py` | Add `get_by_emails` and `_promote_seed_admins` tests |
| `tests/test_auth.py` | Add `_maybe_promote_to_admin` tests |
| `tests/test_admin.py` | Add demotion guard tests |
| `.env.example` | Add `ADMIN_EMAILS=` with comment |
| `docker-compose.yml` | Add `ADMIN_EMAILS: ${ADMIN_EMAILS:-}` to backend env |

---

## Task 1: Config — csv coerce class and ADMIN_EMAILS field

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_config.py`:

```python
def test_admin_emails_parses_csv(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "alice@test.com,bob@test.com")
    from app.config import settings
    assert settings.ADMIN_EMAILS == ["alice@test.com", "bob@test.com"]


def test_admin_emails_strips_whitespace(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", " alice@test.com , bob@test.com ")
    from app.config import settings
    assert settings.ADMIN_EMAILS == ["alice@test.com", "bob@test.com"]


def test_admin_emails_empty_string_returns_empty_list(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "")
    from app.config import settings
    assert settings.ADMIN_EMAILS == []


def test_admin_emails_unset_returns_empty_list(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    from app.config import settings
    assert settings.ADMIN_EMAILS == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
teststack run -- tests/test_config.py -v
```

Expected: FAIL — `settings` has no `ADMIN_EMAILS` attribute.

- [ ] **Step 3: Add csv coerce class and ADMIN_EMAILS to config**

Replace the contents of `backend/app/config.py`:

```python
import figenv


class csv:
    @staticmethod
    def _coerce(value):
        return [v.strip() for v in value.split(",") if v.strip()]


class Config(metaclass=figenv.MetaConfig):
    DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/northlanding"
    SECRET_KEY = "change-me"
    GOOGLE_CLIENT_ID = ""
    GOOGLE_CLIENT_SECRET = ""
    TWILIO_ACCOUNT_SID = ""
    TWILIO_AUTH_TOKEN = ""
    TWILIO_FROM_NUMBER = ""
    SUPABASE_URL = ""
    SUPABASE_SERVICE_KEY = ""
    SUPABASE_BUCKET = "disc-photos"
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = 60
    FRONTEND_URL = "http://localhost:5173"
    ADMIN_EMAILS: csv = ""


settings = Config
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
teststack run -- tests/test_config.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat: add ADMIN_EMAILS config with csv coerce"
```

---

## Task 2: UserRepository — get_by_emails method

**Files:**
- Modify: `backend/app/repositories/user.py`
- Modify: `backend/tests/test_lifespan.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `backend/tests/test_lifespan.py`:

```python
import pytest
from app.repositories.user import UserRepository


@pytest.mark.asyncio
async def test_get_by_emails_returns_matching_users(db):
    repo = UserRepository(db)
    u1 = await repo.create(name="A", email="a@test.com", google_id="g-a")
    u2 = await repo.create(name="B", email="b@test.com", google_id="g-b")
    await repo.create(name="C", email="c@test.com", google_id="g-c")
    result = await repo.get_by_emails(["a@test.com", "b@test.com"])
    ids = {u.id for u in result}
    assert u1.id in ids
    assert u2.id in ids
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_by_emails_returns_empty_for_empty_list(db):
    repo = UserRepository(db)
    result = await repo.get_by_emails([])
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
teststack run -- tests/test_lifespan.py::test_get_by_emails_returns_matching_users tests/test_lifespan.py::test_get_by_emails_returns_empty_for_empty_list -v
```

Expected: FAIL — `UserRepository` has no `get_by_emails` method.

- [ ] **Step 3: Add get_by_emails to UserRepository**

Add this method to the `UserRepository` class in `backend/app/repositories/user.py`, after `get_by_google_id`:

```python
    async def get_by_emails(self, emails: list[str]) -> list[User]:
        if not emails:
            return []
        result = await self.db.execute(select(User).where(User.email.in_(emails)))
        return list(result.scalars().all())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
teststack run -- tests/test_lifespan.py::test_get_by_emails_returns_matching_users tests/test_lifespan.py::test_get_by_emails_returns_empty_for_empty_list -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/user.py backend/tests/test_lifespan.py
git commit -m "feat: add UserRepository.get_by_emails"
```

---

## Task 3: Startup seed admin promotion

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_lifespan.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `backend/tests/test_lifespan.py` (after the get_by_emails tests added in Task 2):

```python
from app.main import _promote_seed_admins


@pytest.mark.asyncio
async def test_promote_seed_admins_promotes_matching_user(db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "alice@test.com")
    repo = UserRepository(db)
    user = await repo.create(name="Alice", email="alice@test.com", google_id="g-alice")
    await _promote_seed_admins(db)
    await db.refresh(user)
    assert user.is_admin is True


@pytest.mark.asyncio
async def test_promote_seed_admins_skips_already_admin(db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "alice@test.com")
    repo = UserRepository(db)
    user = await repo.create(name="Alice", email="alice@test.com", google_id="g-alice2")
    user.is_admin = True
    await db.flush()
    await _promote_seed_admins(db)
    await db.refresh(user)
    assert user.is_admin is True


@pytest.mark.asyncio
async def test_promote_seed_admins_skips_when_env_empty(db, monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    repo = UserRepository(db)
    user = await repo.create(name="Bob", email="bob@test.com", google_id="g-bob")
    await _promote_seed_admins(db)
    await db.refresh(user)
    assert user.is_admin is False


@pytest.mark.asyncio
async def test_promote_seed_admins_skips_nonexistent_email(db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "ghost@test.com")
    await _promote_seed_admins(db)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
teststack run -- tests/test_lifespan.py::test_promote_seed_admins_promotes_matching_user tests/test_lifespan.py::test_promote_seed_admins_skips_already_admin tests/test_lifespan.py::test_promote_seed_admins_skips_when_env_empty tests/test_lifespan.py::test_promote_seed_admins_skips_nonexistent_email -v
```

Expected: FAIL — `_promote_seed_admins` not imported from `app.main`.

- [ ] **Step 3: Add _promote_seed_admins and wire into lifespan**

Replace `backend/app/main.py` with:

```python
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import AsyncSessionLocal
from app.repositories.user import UserRepository
from app.routers import auth, discs, users, admin, webhooks
from app.services.storage import get_storage_client

logger = logging.getLogger(__name__)


async def _ensure_storage_bucket() -> None:
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        return

    def _create():
        client = get_storage_client()
        try:
            client.storage.create_bucket(settings.SUPABASE_BUCKET, options={"public": True})
        except Exception as e:
            logger.warning("Storage bucket creation skipped: %s", e)

    await asyncio.to_thread(_create)


async def _promote_seed_admins(db: AsyncSession) -> None:
    emails = settings.ADMIN_EMAILS
    if not emails:
        return
    repo = UserRepository(db)
    users = await repo.get_by_emails(emails)
    for user in users:
        if not user.is_admin:
            await repo.update(user, is_admin=True)
    await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _ensure_storage_bucket()
    async with AsyncSessionLocal() as db:
        await _promote_seed_admins(db)
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

- [ ] **Step 4: Run tests to verify they pass**

```bash
teststack run -- tests/test_lifespan.py -v
```

Expected: all tests PASS (including the 3 pre-existing storage bucket tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_lifespan.py
git commit -m "feat: promote seed admins on startup"
```

---

## Task 4: Auth-time promotion on login

**Files:**
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `backend/tests/test_auth.py`:

```python
from app.repositories.user import UserRepository
from app.routers.auth import _maybe_promote_to_admin


async def test_maybe_promote_to_admin_promotes_seed_email(db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "alice@test.com")
    repo = UserRepository(db)
    user = await repo.create(name="Alice", email="alice@test.com", google_id="g-alice")
    await _maybe_promote_to_admin(user, "alice@test.com", repo, db)
    await db.refresh(user)
    assert user.is_admin is True


async def test_maybe_promote_to_admin_skips_non_seed_email(db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "seed@test.com")
    repo = UserRepository(db)
    user = await repo.create(name="Bob", email="bob@test.com", google_id="g-bob")
    await _maybe_promote_to_admin(user, "bob@test.com", repo, db)
    await db.refresh(user)
    assert user.is_admin is False


async def test_maybe_promote_to_admin_skips_already_admin(db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "alice@test.com")
    repo = UserRepository(db)
    user = await repo.create(name="Alice", email="alice@test.com", google_id="g-alice2")
    user.is_admin = True
    await db.flush()
    await _maybe_promote_to_admin(user, "alice@test.com", repo, db)
    assert user.is_admin is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
teststack run -- tests/test_auth.py::test_maybe_promote_to_admin_promotes_seed_email tests/test_auth.py::test_maybe_promote_to_admin_skips_non_seed_email tests/test_auth.py::test_maybe_promote_to_admin_skips_already_admin -v
```

Expected: FAIL — `_maybe_promote_to_admin` not importable from `app.routers.auth`.

- [ ] **Step 3: Add _maybe_promote_to_admin helper and call it in the callback**

Replace `backend/app/routers/auth.py` with:

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.auth import create_access_token

router = APIRouter()

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


async def _maybe_promote_to_admin(
    user: User, email: str, repo: UserRepository, db: AsyncSession
) -> None:
    if email in settings.ADMIN_EMAILS and not user.is_admin:
        await repo.update(user, is_admin=True)
        await db.commit()


@router.get("/google", operation_id="googleLogin")
async def login_google(request: Request):
    redirect_uri = str(request.url_for("auth_google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="auth_google_callback", operation_id="googleCallback")
async def auth_google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(status_code=400, detail="Google auth failed")

    repo = UserRepository(db)
    user = await repo.get_by_google_id(user_info["sub"])
    if user is None:
        user = await repo.create(
            name=user_info.get("name", user_info["email"]),
            email=user_info["email"],
            google_id=user_info["sub"],
        )
        await db.commit()

    await _maybe_promote_to_admin(user, user_info["email"], repo, db)

    access_token = create_access_token(str(user.id))
    redirect_url = f"{settings.FRONTEND_URL}/auth/callback?token={access_token}"
    return RedirectResponse(url=redirect_url)


@router.post("/logout", operation_id="logout")
async def logout():
    return {"message": "logged out"}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
teststack run -- tests/test_auth.py -v
```

Expected: all tests PASS (including 3 pre-existing auth tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth.py
git commit -m "feat: promote seed admins at login time"
```

---

## Task 5: Demotion guard in admin update endpoint

**Files:**
- Modify: `backend/app/routers/admin.py`
- Modify: `backend/tests/test_admin.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `backend/tests/test_admin.py`:

```python
async def test_cannot_demote_seed_admin(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "seed@test.com")
    admin = await make_admin_user(db)
    repo = UserRepository(db)
    seed = await repo.create(name="Seed", email="seed@test.com", google_id="g-seed")
    seed.is_admin = True
    await db.commit()

    resp = await client.patch(
        f"/admin/users/{seed.id}",
        json={"is_admin": False},
        headers=admin_token(admin.id),
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Cannot demote a seed admin"


async def test_can_demote_non_seed_admin(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "seed@test.com")
    admin = await make_admin_user(db)
    repo = UserRepository(db)
    other = await repo.create(name="Other", email="other@test.com", google_id="g-other")
    other.is_admin = True
    await db.commit()

    resp = await client.patch(
        f"/admin/users/{other.id}",
        json={"is_admin": False},
        headers=admin_token(admin.id),
    )
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
teststack run -- tests/test_admin.py::test_cannot_demote_seed_admin tests/test_admin.py::test_can_demote_non_seed_admin -v
```

Expected: `test_cannot_demote_seed_admin` FAIL (returns 200 not 403); `test_can_demote_non_seed_admin` PASS.

- [ ] **Step 3: Add demotion guard to update_user**

In `backend/app/routers/admin.py`, add `from app.config import settings` to the imports block (after the existing imports), then add the guard inside `update_user` after the 404 check:

The full updated `update_user` function:

```python
@router.patch("/users/{user_id}", response_model=UserOut, operation_id="adminUpdateUser")
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if body.is_admin is False and user.email in settings.ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Cannot demote a seed admin")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    user = await repo.update(user, **updates)
    await db.commit()
    return user
```

Also add this import at the top of `backend/app/routers/admin.py` (after the existing imports):

```python
from app.config import settings
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
teststack run -- tests/test_admin.py -v
```

Expected: all tests PASS (including all pre-existing admin tests).

- [ ] **Step 5: Run the full test suite**

```bash
teststack run -- -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_admin.py
git commit -m "feat: guard seed admins from demotion via admin API"
```

---

## Task 6: Update config files

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add ADMIN_EMAILS to .env.example**

In `.env.example`, add after the `FRONTEND_URL` section (or at the end):

```
# Comma-separated list of emails that are always admins (promoted on startup and at login)
# Seed admins cannot be demoted via the admin API.
ADMIN_EMAILS=
```

- [ ] **Step 2: Add ADMIN_EMAILS to docker-compose.yml backend environment**

In `docker-compose.yml`, in the `backend` service's `environment` block, add after `FRONTEND_URL`:

```yaml
      ADMIN_EMAILS: ${ADMIN_EMAILS:-}
```

- [ ] **Step 3: Commit**

```bash
git add .env.example docker-compose.yml
git commit -m "chore: document ADMIN_EMAILS in env example and docker-compose"
```
