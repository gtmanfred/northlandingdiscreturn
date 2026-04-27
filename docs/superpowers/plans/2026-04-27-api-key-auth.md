# API Key Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to generate one personal API key (with one-time plaintext display) for authenticating API calls without OAuth, using HMAC-SHA256 hashing with a server-side secret.

**Architecture:** New `api_keys` table (one row per user). Plaintext key has prefix `hou_`, hashed via HMAC-SHA256 with `API_KEY_HMAC_SECRET`. `get_current_user` dependency tries API-key path when the token has the prefix, otherwise falls through to existing JWT decode. Three endpoints under `/users/me/api-key` (POST/GET/DELETE).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, asyncpg, pytest + pytest-asyncio, httpx AsyncClient.

**Spec:** `docs/superpowers/specs/2026-04-27-api-key-auth-design.md`

---

## File Structure

**Created:**
- `backend/app/auth/__init__.py` — empty marker for new package.
- `backend/app/auth/api_key.py` — pure helpers: `generate_api_key`, `hash_api_key`, `looks_like_api_key`, `API_KEY_PREFIX`.
- `backend/app/models/api_key.py` — SQLAlchemy model for `api_keys`.
- `backend/app/repositories/api_key.py` — repository with CRUD by user_id and lookup by hash.
- `backend/app/routers/api_keys.py` — FastAPI router for POST/GET/DELETE `/users/me/api-key`.
- `backend/alembic/versions/<rev>_add_api_keys_table.py` — migration.
- `backend/tests/test_api_keys.py` — endpoint + auth tests.

**Modified:**
- `backend/app/config.py` — add `API_KEY_HMAC_SECRET`.
- `backend/app/deps.py` — branch on prefix, look up key, fall through to JWT.
- `backend/app/main.py` — register the new router.
- `backend/.env.example` — add `API_KEY_HMAC_SECRET`.
- `.env.example` (repo root) — add `API_KEY_HMAC_SECRET`.
- `docker-compose.yml` — pass `API_KEY_HMAC_SECRET` into backend service.
- `backend/teststack.toml` — set test value for `API_KEY_HMAC_SECRET`.

---

## Task 1: Add `API_KEY_HMAC_SECRET` config

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `backend/teststack.toml`

- [ ] **Step 1: Add the setting to `backend/app/config.py`**

Insert after the `JWT_ALGORITHM = "HS256"` line:

```python
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = 60
    REFRESH_TOKEN_EXPIRE_DAYS = 30
    API_KEY_HMAC_SECRET = ""
    FRONTEND_URL = "http://localhost:5173"
```

- [ ] **Step 2: Add to `backend/.env.example`**

Append a new line at the end:

```
API_KEY_HMAC_SECRET=replace-with-random-secret
```

- [ ] **Step 3: Add to root `.env.example`**

Append after the `SECRET_KEY=` block (before `# Postgres password`):

```

# HMAC secret for hashing API keys — generate with: python -c "import secrets; print(secrets.token_hex(32))"
API_KEY_HMAC_SECRET=
```

- [ ] **Step 4: Add to `docker-compose.yml` backend service env**

Add a line in the `backend` service `environment` block, immediately after `SECRET_KEY: ${SECRET_KEY}`:

```yaml
      SECRET_KEY: ${SECRET_KEY}
      API_KEY_HMAC_SECRET: ${API_KEY_HMAC_SECRET}
      GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID:-}
```

- [ ] **Step 5: Add to `backend/teststack.toml`**

Add a line in the `[tests.environment]` section, after `SECRET_KEY`:

```toml
SECRET_KEY = "test-secret-key-for-tests-only"
API_KEY_HMAC_SECRET = "test-api-key-hmac-secret"
GOOGLE_CLIENT_ID = "test-client-id"
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/.env.example .env.example docker-compose.yml backend/teststack.toml
git commit -m "config: add API_KEY_HMAC_SECRET setting"
```

---

## Task 2: Add API key crypto helpers

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/api_key.py`
- Test: `backend/tests/test_api_keys.py`

- [ ] **Step 1: Create the `auth` package marker**

Create empty `backend/app/auth/__init__.py`:

```python
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_api_keys.py`:

```python
import pytest
from app.auth.api_key import (
    API_KEY_PREFIX,
    generate_api_key,
    hash_api_key,
    looks_like_api_key,
)


def test_generate_returns_prefixed_plaintext_hash_and_last_four():
    plaintext, key_hash, last_four = generate_api_key()
    assert plaintext.startswith(API_KEY_PREFIX)
    assert len(plaintext) > len(API_KEY_PREFIX) + 20
    assert last_four == plaintext[-4:]
    assert key_hash == hash_api_key(plaintext)


def test_generate_produces_unique_values():
    a, _, _ = generate_api_key()
    b, _, _ = generate_api_key()
    assert a != b


def test_hash_is_deterministic():
    plaintext, key_hash, _ = generate_api_key()
    assert hash_api_key(plaintext) == key_hash


def test_hash_requires_secret(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "API_KEY_HMAC_SECRET", "")
    with pytest.raises(RuntimeError):
        hash_api_key("hou_anything")


def test_looks_like_api_key():
    assert looks_like_api_key("hou_abc")
    assert not looks_like_api_key("eyJhbGciOi...")
    assert not looks_like_api_key("")
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_api_keys.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth.api_key'`.

- [ ] **Step 4: Implement the helpers**

Create `backend/app/auth/api_key.py`:

```python
import hashlib
import hmac
import secrets
from app.config import settings

API_KEY_PREFIX = "hou_"


def generate_api_key() -> tuple[str, str, str]:
    plaintext = API_KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = hash_api_key(plaintext)
    last_four = plaintext[-4:]
    return plaintext, key_hash, last_four


def hash_api_key(plaintext: str) -> str:
    secret = settings.API_KEY_HMAC_SECRET
    if not secret:
        raise RuntimeError("API_KEY_HMAC_SECRET is not configured")
    return hmac.new(secret.encode("utf-8"), plaintext.encode("utf-8"), hashlib.sha256).hexdigest()


def looks_like_api_key(token: str) -> bool:
    return token.startswith(API_KEY_PREFIX)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_api_keys.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth/__init__.py backend/app/auth/api_key.py backend/tests/test_api_keys.py
git commit -m "feat(auth): add API key crypto helpers"
```

---

## Task 3: Add `ApiKey` model and Alembic migration

**Files:**
- Create: `backend/app/models/api_key.py`
- Create: `backend/alembic/versions/<new_rev>_add_api_keys_table.py`
- Modify: `backend/app/models/__init__.py` (if exists — see Step 1)

- [ ] **Step 1: Inspect models package**

```bash
cat backend/app/models/__init__.py 2>/dev/null
ls backend/app/models/
```

Note: the project's other models are imported directly where used; no central registry. Skip touching `__init__.py` unless it lists models.

- [ ] **Step 2: Create the SQLAlchemy model**

Create `backend/app/models/api_key.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    key_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 3: Ensure model is imported so metadata sees it**

The test conftest creates tables from `Base.metadata`, which only includes models that have been imported. Add an import to `backend/app/main.py` so the model registers at app startup. Insert this near the other model-related imports (after `from app.repositories.user import UserRepository`):

```python
from app.repositories.user import UserRepository
from app.models import api_key as _api_key_model  # noqa: F401  ensure metadata registration
from app.routers import auth, discs, users, admin, webhooks, suggestions, public_calendar
```

(The trailing `# noqa: F401` keeps linters quiet.)

- [ ] **Step 4: Generate the Alembic migration**

```bash
cd backend && uv run alembic revision -m "add_api_keys_table"
```

Find the resulting filename:

```bash
ls -t backend/alembic/versions/ | head -1
```

- [ ] **Step 5: Fill in the migration**

Open the new file and replace the body with:

```python
"""add_api_keys_table

Revision ID: <generated>
Revises: faadcb5befeb
Create Date: <generated>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = '<generated>'
down_revision: Union[str, Sequence[str], None] = '45d1b38444eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("last_four", sa.String(length=4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_api_keys_user_id"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
```

**Important:** Verify `down_revision` matches the latest existing revision. Run:

```bash
cd backend && uv run alembic heads
```

If `faadcb5befeb` is the head, set `down_revision = 'faadcb5befeb'`. If `45d1b38444eb` is the head, use that. Use whichever is reported. (At time of writing the heads command will identify the current head; pick the single value reported.)

- [ ] **Step 6: Verify migration runs cleanly**

```bash
cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head
```

Expected: all three commands complete without errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/api_key.py backend/app/main.py backend/alembic/versions/
git commit -m "feat(db): add api_keys table and model"
```

---

## Task 4: Add `ApiKeyRepository`

**Files:**
- Create: `backend/app/repositories/api_key.py`
- Test: `backend/tests/test_api_keys.py`

- [ ] **Step 1: Add repository tests**

Append to `backend/tests/test_api_keys.py`:

```python
from app.repositories.user import UserRepository
from app.repositories.api_key import ApiKeyRepository


async def test_repo_upsert_replaces_existing(db):
    user = await UserRepository(db).create(name="K", email="k@example.com", google_id="g-k")
    repo = ApiKeyRepository(db)

    row1 = await repo.upsert_for_user(user.id, key_hash="h1", last_four="aaaa")
    row2 = await repo.upsert_for_user(user.id, key_hash="h2", last_four="bbbb")

    assert row1.id != row2.id
    fetched = await repo.get_for_user(user.id)
    assert fetched.key_hash == "h2"
    assert fetched.last_four == "bbbb"


async def test_repo_get_by_hash(db):
    user = await UserRepository(db).create(name="K", email="k2@example.com", google_id="g-k2")
    repo = ApiKeyRepository(db)
    await repo.upsert_for_user(user.id, key_hash="hX", last_four="zzzz")

    found = await repo.get_by_hash("hX")
    assert found is not None
    assert found.user_id == user.id

    missing = await repo.get_by_hash("nope")
    assert missing is None


async def test_repo_delete_for_user(db):
    user = await UserRepository(db).create(name="K", email="k3@example.com", google_id="g-k3")
    repo = ApiKeyRepository(db)
    await repo.upsert_for_user(user.id, key_hash="hY", last_four="yyyy")

    deleted = await repo.delete_for_user(user.id)
    assert deleted is True

    deleted_again = await repo.delete_for_user(user.id)
    assert deleted_again is False


async def test_repo_touch_last_used_at(db):
    user = await UserRepository(db).create(name="K", email="k4@example.com", google_id="g-k4")
    repo = ApiKeyRepository(db)
    row = await repo.upsert_for_user(user.id, key_hash="hZ", last_four="kkkk")
    assert row.last_used_at is None

    await repo.touch_last_used(row.id)
    refreshed = await repo.get_for_user(user.id)
    assert refreshed.last_used_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_api_keys.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.repositories.api_key'`.

- [ ] **Step 3: Implement the repository**

Create `backend/app/repositories/api_key.py`:

```python
import uuid
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from app.models.api_key import ApiKey


class ApiKeyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_for_user(
        self, user_id: uuid.UUID, *, key_hash: str, last_four: str
    ) -> ApiKey:
        await self.db.execute(delete(ApiKey).where(ApiKey.user_id == user_id))
        row = ApiKey(user_id=user_id, key_hash=key_hash, last_four=last_four)
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def get_for_user(self, user_id: uuid.UUID) -> ApiKey | None:
        result = await self.db.execute(select(ApiKey).where(ApiKey.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        result = await self.db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        return result.scalar_one_or_none()

    async def delete_for_user(self, user_id: uuid.UUID) -> bool:
        result = await self.db.execute(delete(ApiKey).where(ApiKey.user_id == user_id))
        return result.rowcount > 0

    async def touch_last_used(self, api_key_id: uuid.UUID) -> None:
        await self.db.execute(
            update(ApiKey).where(ApiKey.id == api_key_id).values(last_used_at=func.now())
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_api_keys.py -v
```

Expected: all 9 tests pass (5 from Task 2 + 4 here).

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/api_key.py backend/tests/test_api_keys.py
git commit -m "feat(repo): add ApiKeyRepository"
```

---

## Task 5: Update `get_current_user` to accept API keys

**Files:**
- Modify: `backend/app/deps.py`
- Test: `backend/tests/test_api_keys.py`

- [ ] **Step 1: Add tests for the dependency**

Append to `backend/tests/test_api_keys.py`:

```python
from app.auth.api_key import generate_api_key


async def test_api_key_authenticates_protected_endpoint(client, db):
    user_repo = UserRepository(db)
    user = await user_repo.create(name="ApiUser", email="api@example.com", google_id="g-api")
    plaintext, key_hash, last_four = generate_api_key()
    await ApiKeyRepository(db).upsert_for_user(user.id, key_hash=key_hash, last_four=last_four)
    await db.commit()

    resp = await client.get("/users/me", headers={"Authorization": f"Bearer {plaintext}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "api@example.com"


async def test_invalid_api_key_returns_401(client, db):
    resp = await client.get(
        "/users/me",
        headers={"Authorization": "Bearer hou_definitely-not-a-real-key"},
    )
    assert resp.status_code == 401


async def test_jwt_still_works(client, db):
    from app.services.auth import create_access_token

    user = await UserRepository(db).create(name="JwtUser", email="jwt@example.com", google_id="g-jwt")
    await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
    resp = await client.get("/users/me", headers=headers)
    assert resp.status_code == 200


async def test_api_key_use_updates_last_used_at(client, db):
    user = await UserRepository(db).create(name="LU", email="lu@example.com", google_id="g-lu")
    plaintext, key_hash, last_four = generate_api_key()
    await ApiKeyRepository(db).upsert_for_user(user.id, key_hash=key_hash, last_four=last_four)
    await db.commit()

    resp = await client.get("/users/me", headers={"Authorization": f"Bearer {plaintext}"})
    assert resp.status_code == 200

    refreshed = await ApiKeyRepository(db).get_for_user(user.id)
    assert refreshed.last_used_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_api_keys.py -v -k "api_key_authenticates or invalid_api_key or jwt_still_works or last_used_at"
```

Expected: `test_api_key_authenticates_protected_endpoint` and `test_invalid_api_key_returns_401` and `test_api_key_use_updates_last_used_at` FAIL with 401 (because the dep doesn't try API keys yet). `test_jwt_still_works` should PASS already.

- [ ] **Step 3: Update `backend/app/deps.py`**

Replace the file with:

```python
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError
from app.database import get_db
from app.services.auth import decode_access_token
from app.repositories.user import UserRepository
from app.repositories.api_key import ApiKeyRepository
from app.auth.api_key import looks_like_api_key, hash_api_key
from app.models.user import User

bearer = HTTPBearer()


async def _user_from_api_key(token: str, db: AsyncSession) -> User | None:
    key_hash = hash_api_key(token)
    api_repo = ApiKeyRepository(db)
    row = await api_repo.get_by_hash(key_hash)
    if row is None:
        return None
    user = await UserRepository(db).get_by_id(row.user_id)
    if user is None:
        return None
    await api_repo.touch_last_used(row.id)
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    token = credentials.credentials

    if looks_like_api_key(token):
        user = await _user_from_api_key(token, db)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        return user

    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise JWTError("Missing sub claim")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user
```

- [ ] **Step 4: Run all api-key tests**

```bash
cd backend && uv run pytest tests/test_api_keys.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full test suite to confirm no regression**

```bash
cd backend && uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/deps.py backend/tests/test_api_keys.py
git commit -m "feat(auth): accept API key in get_current_user"
```

---

## Task 6: Add API key endpoints

**Files:**
- Create: `backend/app/routers/api_keys.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api_keys.py`

- [ ] **Step 1: Add endpoint tests**

Append to `backend/tests/test_api_keys.py`:

```python
from app.services.auth import create_access_token


def jwt_headers(user_id) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


async def test_post_creates_key_and_returns_plaintext_once(client, db):
    user = await UserRepository(db).create(name="P", email="p@example.com", google_id="g-p")
    await db.commit()

    resp = await client.post("/users/me/api-key", headers=jwt_headers(user.id))
    assert resp.status_code == 201
    body = resp.json()
    assert body["api_key"].startswith("hou_")
    assert body["last_four"] == body["api_key"][-4:]
    assert "created_at" in body

    # GET never returns the plaintext
    resp2 = await client.get("/users/me/api-key", headers=jwt_headers(user.id))
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert "api_key" not in body2
    assert body2["last_four"] == body["last_four"]


async def test_post_twice_replaces_existing_key(client, db):
    user = await UserRepository(db).create(name="P2", email="p2@example.com", google_id="g-p2")
    await db.commit()

    first = await client.post("/users/me/api-key", headers=jwt_headers(user.id))
    second = await client.post("/users/me/api-key", headers=jwt_headers(user.id))
    assert second.status_code == 201

    old_key = first.json()["api_key"]
    new_key = second.json()["api_key"]
    assert old_key != new_key

    # Old key no longer authenticates
    bad = await client.get("/users/me", headers={"Authorization": f"Bearer {old_key}"})
    assert bad.status_code == 401

    good = await client.get("/users/me", headers={"Authorization": f"Bearer {new_key}"})
    assert good.status_code == 200


async def test_get_returns_404_when_no_key(client, db):
    user = await UserRepository(db).create(name="P3", email="p3@example.com", google_id="g-p3")
    await db.commit()
    resp = await client.get("/users/me/api-key", headers=jwt_headers(user.id))
    assert resp.status_code == 404


async def test_delete_revokes_key(client, db):
    user = await UserRepository(db).create(name="P4", email="p4@example.com", google_id="g-p4")
    await db.commit()

    created = await client.post("/users/me/api-key", headers=jwt_headers(user.id))
    plaintext = created.json()["api_key"]

    resp = await client.delete("/users/me/api-key", headers=jwt_headers(user.id))
    assert resp.status_code == 204

    bad = await client.get("/users/me", headers={"Authorization": f"Bearer {plaintext}"})
    assert bad.status_code == 401

    # Second delete is 404
    resp2 = await client.delete("/users/me/api-key", headers=jwt_headers(user.id))
    assert resp2.status_code == 404


async def test_endpoints_require_authentication(client):
    assert (await client.post("/users/me/api-key")).status_code == 403
    assert (await client.get("/users/me/api-key")).status_code == 403
    assert (await client.delete("/users/me/api-key")).status_code == 403
```

(`HTTPBearer` returns 403 by default when no credentials are sent; that matches the existing pattern in this codebase.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_api_keys.py -v
```

Expected: new tests fail (404 from FastAPI for unknown route).

- [ ] **Step 3: Create the router**

Create `backend/app/routers/api_keys.py`:

```python
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.repositories.api_key import ApiKeyRepository
from app.auth.api_key import generate_api_key

router = APIRouter()


@router.post("/me/api-key", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    plaintext, key_hash, last_four = generate_api_key()
    repo = ApiKeyRepository(db)
    row = await repo.upsert_for_user(user.id, key_hash=key_hash, last_four=last_four)
    await db.commit()
    return {
        "api_key": plaintext,
        "last_four": row.last_four,
        "created_at": row.created_at,
    }


@router.get("/me/api-key")
async def get_api_key(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    row = await ApiKeyRepository(db).get_for_user(user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No API key")
    return {
        "last_four": row.last_four,
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
    }


@router.delete("/me/api-key", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    deleted = await ApiKeyRepository(db).delete_for_user(user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No API key")
    await db.commit()
```

- [ ] **Step 4: Register the router in `backend/app/main.py`**

Update the imports line:

```python
from app.routers import auth, discs, users, admin, webhooks, suggestions, public_calendar, api_keys
```

Add an `include_router` call after the existing `users` router registration:

```python
    app.include_router(users.router, prefix="/users", tags=["users"])
    app.include_router(api_keys.router, prefix="/users", tags=["api-keys"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
```

- [ ] **Step 5: Run the full test file**

```bash
cd backend && uv run pytest tests/test_api_keys.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Run the full test suite**

```bash
cd backend && uv run pytest -q
```

Expected: full suite passes.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/api_keys.py backend/app/main.py backend/tests/test_api_keys.py
git commit -m "feat(api): add /users/me/api-key endpoints"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run full test suite from a clean state**

```bash
cd backend && uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Verify migration round-trips**

```bash
cd backend && uv run alembic downgrade base && uv run alembic upgrade head
```

Expected: clean apply.

- [ ] **Step 3: Manual smoke test (optional, requires docker-compose)**

```bash
# In one terminal
docker compose up

# In another, after auth via the frontend, grab a JWT and:
curl -X POST http://localhost:8000/users/me/api-key -H "Authorization: Bearer <jwt>"
# capture the api_key from the response, then:
curl http://localhost:8000/users/me -H "Authorization: Bearer hou_..."
```

Expected: first request returns the plaintext + last_four + created_at. Second request returns the user.
