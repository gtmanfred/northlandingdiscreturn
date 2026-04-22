# Auth Auto-Logout & Refresh Token Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auto-logout on token expiry and a 30-day httpOnly refresh token cookie so users stay logged in across revisits without re-authenticating via Google every hour.

**Architecture:** Short-lived (60 min) access JWT in localStorage unchanged. A new opaque refresh token stored in the `users` table is issued as an httpOnly cookie on Google OAuth callback. A new `POST /auth/refresh` endpoint exchanges a valid cookie for a new access JWT and rotates the refresh token. The frontend Axios response interceptor catches 401s, attempts a silent refresh, and retries; on startup, `AuthContext` also silently refreshes an expired stored token before rendering protected routes.

**Tech Stack:** FastAPI (Python), SQLAlchemy async, Alembic, python-jose, React, Axios, Vitest, @testing-library/react

---

## File Structure

| File | Change |
|------|--------|
| `backend/app/models/user.py` | Add `refresh_token` and `refresh_token_expires_at` columns |
| `backend/app/config.py` | Add `REFRESH_TOKEN_EXPIRE_DAYS = 30` |
| `backend/app/services/auth.py` | Add `create_refresh_token()` |
| `backend/app/repositories/user.py` | Add `get_by_refresh_token()` |
| `backend/app/routers/auth.py` | Update callback to set cookie; add `/auth/refresh`; update `/auth/logout` |
| `backend/alembic/versions/<rev>_add_refresh_token_to_users.py` | New migration |
| `backend/tests/test_auth.py` | Add tests for refresh and logout endpoints |
| `frontend/src/api/client.ts` | Export `API_URL`; add `withCredentials`; add 401 response interceptor |
| `frontend/src/auth/AuthContext.tsx` | Add `isInitializing`; silent refresh on mount; update `logout()` |
| `frontend/src/auth/ProtectedRoute.tsx` | Show loading while `isInitializing` |
| `frontend/src/main.tsx` | Fix React Query retry config to skip 401s |
| `frontend/src/auth/AuthContext.test.tsx` | Update tests for new startup and logout behavior |

---

## Task 1: User model columns + config setting

**Files:**
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Write a failing test that asserts the new columns exist on the User model**

Add to `backend/tests/test_auth.py`:

```python
def test_user_model_has_refresh_token_columns():
    from sqlalchemy import inspect
    from app.models.user import User
    mapper = inspect(User)
    cols = {c.key for c in mapper.attrs}
    assert "refresh_token" in cols
    assert "refresh_token_expires_at" in cols
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd backend && pytest tests/test_auth.py::test_user_model_has_refresh_token_columns -v
```

Expected: `FAILED` — `AssertionError`

- [ ] **Step 3: Add columns to the User model**

In `backend/app/models/user.py`, replace the class body (add after `created_at`):

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    google_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    refresh_token: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    phone_numbers: Mapped[list["PhoneNumber"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
```

- [ ] **Step 4: Add config setting**

In `backend/app/config.py`, add after `JWT_EXPIRE_MINUTES`:

```python
REFRESH_TOKEN_EXPIRE_DAYS = 30
```

- [ ] **Step 5: Run test to confirm it passes**

```bash
cd backend && pytest tests/test_auth.py::test_user_model_has_refresh_token_columns -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/user.py backend/app/config.py backend/tests/test_auth.py
git commit -m "feat: add refresh_token columns to User model"
```

---

## Task 2: `create_refresh_token` service function

**Files:**
- Modify: `backend/app/services/auth.py`
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_auth.py`:

```python
def test_create_refresh_token_returns_64_char_hex():
    from app.services.auth import create_refresh_token
    token = create_refresh_token()
    assert len(token) == 64
    assert all(c in "0123456789abcdef" for c in token)


def test_create_refresh_token_is_unique():
    from app.services.auth import create_refresh_token
    assert create_refresh_token() != create_refresh_token()
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd backend && pytest tests/test_auth.py::test_create_refresh_token_returns_64_char_hex tests/test_auth.py::test_create_refresh_token_is_unique -v
```

Expected: `FAILED` — `ImportError` (function does not exist yet)

- [ ] **Step 3: Add `create_refresh_token` to the auth service**

In `backend/app/services/auth.py`, `secrets` is already imported. Add after `generate_verification_code`:

```python
def create_refresh_token() -> str:
    return secrets.token_hex(32)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && pytest tests/test_auth.py::test_create_refresh_token_returns_64_char_hex tests/test_auth.py::test_create_refresh_token_is_unique -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth.py backend/tests/test_auth.py
git commit -m "feat: add create_refresh_token service function"
```

---

## Task 3: `UserRepository.get_by_refresh_token`

**Files:**
- Modify: `backend/app/repositories/user.py`
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_auth.py`:

```python
from datetime import datetime, timezone, timedelta


async def test_get_by_refresh_token_returns_user(db):
    from app.repositories.user import UserRepository
    repo = UserRepository(db)
    user = await repo.create(name="RefTest", email="reftest@example.com", google_id="g-reftest")
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    await repo.update(user, refresh_token="abc123token", refresh_token_expires_at=expires)
    found = await repo.get_by_refresh_token("abc123token")
    assert found is not None
    assert found.id == user.id


async def test_get_by_refresh_token_returns_none_for_unknown(db):
    from app.repositories.user import UserRepository
    repo = UserRepository(db)
    result = await repo.get_by_refresh_token("nonexistent-token")
    assert result is None
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd backend && pytest tests/test_auth.py::test_get_by_refresh_token_returns_user tests/test_auth.py::test_get_by_refresh_token_returns_none_for_unknown -v
```

Expected: `FAILED` — `AttributeError` (method does not exist yet)

- [ ] **Step 3: Add `get_by_refresh_token` to the repository**

In `backend/app/repositories/user.py`, add after `get_by_google_id`:

```python
    async def get_by_refresh_token(self, refresh_token: str) -> User | None:
        result = await self.db.execute(select(User).where(User.refresh_token == refresh_token))
        return result.scalar_one_or_none()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && pytest tests/test_auth.py::test_get_by_refresh_token_returns_user tests/test_auth.py::test_get_by_refresh_token_returns_none_for_unknown -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/user.py backend/tests/test_auth.py
git commit -m "feat: add get_by_refresh_token to UserRepository"
```

---

## Task 4: Alembic migration

**Files:**
- Create: `backend/alembic/versions/<rev>_add_refresh_token_to_users.py`

- [ ] **Step 1: Generate the migration from the model diff**

```bash
cd backend && alembic revision --autogenerate -m "add_refresh_token_to_users"
```

Expected output: `Generating .../backend/alembic/versions/<rev_id>_add_refresh_token_to_users.py ... done`

- [ ] **Step 2: Open the generated file and verify it contains both column additions**

The file should contain an `upgrade()` that looks like:

```python
def upgrade() -> None:
    op.add_column("users", sa.Column("refresh_token", sa.String(), nullable=True))
    op.add_column("users", sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(None, "users", ["refresh_token"])


def downgrade() -> None:
    op.drop_constraint(<constraint_name>, "users", type_="unique")
    op.drop_column("users", "refresh_token_expires_at")
    op.drop_column("users", "refresh_token")
```

If `autogenerate` produced different column types or missed the unique constraint, adjust manually to match the above.

- [ ] **Step 3: Verify `down_revision` is set to `'725ccbfb76ab'`**

Open the file. The header should read:
```python
down_revision: Union[str, Sequence[str], None] = '725ccbfb76ab'
```

- [ ] **Step 4: Run the migration against the dev database**

```bash
cd backend && alembic upgrade head
```

Expected: no errors, new migration applied.

- [ ] **Step 5: Commit the migration**

```bash
git add backend/alembic/versions/
git commit -m "feat: migration — add refresh_token columns to users"
```

---

## Task 5: `POST /auth/refresh` endpoint

**Files:**
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_auth.py`:

```python
async def test_refresh_returns_new_access_token(client, db):
    from app.repositories.user import UserRepository
    from app.services.auth import create_refresh_token
    repo = UserRepository(db)
    user = await repo.create(name="Refresher", email="refresher@example.com", google_id="g-refresher")
    token_value = create_refresh_token()
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    await repo.update(user, refresh_token=token_value, refresh_token_expires_at=expires)
    await db.commit()

    response = await client.post("/auth/refresh", cookies={"refresh_token": token_value})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert isinstance(data["token"], str)


async def test_refresh_rotates_token(client, db):
    from app.repositories.user import UserRepository
    from app.services.auth import create_refresh_token
    repo = UserRepository(db)
    user = await repo.create(name="Rotator", email="rotator@example.com", google_id="g-rotator")
    original = create_refresh_token()
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    await repo.update(user, refresh_token=original, refresh_token_expires_at=expires)
    await db.commit()

    response = await client.post("/auth/refresh", cookies={"refresh_token": original})
    assert response.status_code == 200

    response2 = await client.post("/auth/refresh", cookies={"refresh_token": original})
    assert response2.status_code == 401


async def test_refresh_returns_401_for_unknown_token(client):
    response = await client.post("/auth/refresh", cookies={"refresh_token": "bad-token"})
    assert response.status_code == 401


async def test_refresh_returns_401_for_expired_token(client, db):
    from app.repositories.user import UserRepository
    from app.services.auth import create_refresh_token
    repo = UserRepository(db)
    user = await repo.create(name="Expiry", email="expiry@example.com", google_id="g-expiry")
    token_value = create_refresh_token()
    expires = datetime.now(timezone.utc) - timedelta(days=1)
    await repo.update(user, refresh_token=token_value, refresh_token_expires_at=expires)
    await db.commit()

    response = await client.post("/auth/refresh", cookies={"refresh_token": token_value})
    assert response.status_code == 401


async def test_refresh_returns_401_when_cookie_missing(client):
    response = await client.post("/auth/refresh")
    assert response.status_code == 401
```

- [ ] **Step 2: Run to confirm they all fail**

```bash
cd backend && pytest tests/test_auth.py::test_refresh_returns_new_access_token tests/test_auth.py::test_refresh_rotates_token tests/test_auth.py::test_refresh_returns_401_for_unknown_token tests/test_auth.py::test_refresh_returns_401_for_expired_token tests/test_auth.py::test_refresh_returns_401_when_cookie_missing -v
```

Expected: all `FAILED` — `404 Not Found` (endpoint doesn't exist yet)

- [ ] **Step 3: Add the refresh endpoint to `backend/app/routers/auth.py`**

Replace the import block at the top of `auth.py` with these lines (adds `Cookie`, `JSONResponse`, `datetime` imports and `create_refresh_token`):

```python
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.auth import create_access_token, create_refresh_token
```

Add the endpoint after `auth_google_callback`:

```python
@router.post("/refresh", operation_id="refreshToken")
async def refresh_token(
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    repo = UserRepository(db)
    user = await repo.get_by_refresh_token(refresh_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if user.refresh_token_expires_at is None or user.refresh_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")

    new_access_token = create_access_token(str(user.id))
    new_refresh_token = create_refresh_token()
    new_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    await repo.update(user, refresh_token=new_refresh_token, refresh_token_expires_at=new_expires)
    await db.commit()

    cookie_secure = settings.FRONTEND_URL.startswith("https://")
    response = JSONResponse(content={"token": new_access_token})
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=60 * 60 * 24 * settings.REFRESH_TOKEN_EXPIRE_DAYS,
        path="/",
    )
    return response
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && pytest tests/test_auth.py::test_refresh_returns_new_access_token tests/test_auth.py::test_refresh_rotates_token tests/test_auth.py::test_refresh_returns_401_for_unknown_token tests/test_auth.py::test_refresh_returns_401_for_expired_token tests/test_auth.py::test_refresh_returns_401_when_cookie_missing -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth.py
git commit -m "feat: add POST /auth/refresh endpoint with token rotation"
```

---

## Task 6: Update `/auth/logout` and Google callback cookie

**Files:**
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing tests for the updated logout**

Add to `backend/tests/test_auth.py`:

```python
async def test_logout_clears_refresh_token_in_db(client, db):
    from app.repositories.user import UserRepository
    from app.services.auth import create_refresh_token
    repo = UserRepository(db)
    user = await repo.create(name="LogoutUser", email="logoutuser@example.com", google_id="g-logout")
    token_value = create_refresh_token()
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    await repo.update(user, refresh_token=token_value, refresh_token_expires_at=expires)
    await db.commit()

    response = await client.post("/auth/logout", cookies={"refresh_token": token_value})
    assert response.status_code == 200

    await db.refresh(user)
    assert user.refresh_token is None
    assert user.refresh_token_expires_at is None


async def test_logout_without_cookie_returns_200(client):
    response = await client.post("/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"message": "logged out"}
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd backend && pytest tests/test_auth.py::test_logout_clears_refresh_token_in_db tests/test_auth.py::test_logout_without_cookie_returns_200 -v
```

Expected: `test_logout_clears_refresh_token_in_db` — `FAILED` (refresh_token not cleared); `test_logout_without_cookie_returns_200` — `PASSED` (already returns 200)

- [ ] **Step 3: Update the logout endpoint in `backend/app/routers/auth.py`**

Replace the existing `logout` function:

```python
@router.post("/logout", operation_id="logout")
async def logout(
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if refresh_token:
        repo = UserRepository(db)
        user = await repo.get_by_refresh_token(refresh_token)
        if user is not None:
            await repo.update(user, refresh_token=None, refresh_token_expires_at=None)
            await db.commit()

    cookie_secure = settings.FRONTEND_URL.startswith("https://")
    response = JSONResponse(content={"message": "logged out"})
    response.set_cookie(
        key="refresh_token",
        value="",
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=0,
        path="/",
    )
    return response
```

- [ ] **Step 4: Update `auth_google_callback` to issue the refresh token cookie**

Replace the existing `auth_google_callback` return block (last 3 lines of the function):

```python
    access_token = create_access_token(str(user.id))
    new_refresh_token = create_refresh_token()
    new_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    await repo.update(user, refresh_token=new_refresh_token, refresh_token_expires_at=new_expires)
    await db.commit()

    cookie_secure = settings.FRONTEND_URL.startswith("https://")
    redirect_url = f"{settings.FRONTEND_URL}/auth/callback?token={access_token}"
    response = RedirectResponse(url=redirect_url)
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=60 * 60 * 24 * settings.REFRESH_TOKEN_EXPIRE_DAYS,
        path="/",
    )
    return response
```

Note: `JSONResponse` must be imported. Update the imports at the top of `auth.py` to:

```python
from fastapi.responses import JSONResponse, RedirectResponse
```

- [ ] **Step 5: Run all auth tests**

```bash
cd backend && pytest tests/test_auth.py -v
```

Expected: all `PASSED`

- [ ] **Step 6: Run the full backend test suite**

```bash
cd backend && pytest -v
```

Expected: all `PASSED` — no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth.py
git commit -m "feat: update /auth/logout and /auth/google/callback to manage refresh token cookie"
```

---

## Task 7: Frontend `client.ts` — withCredentials + 401 interceptor

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Replace the full contents of `frontend/src/api/client.ts`**

```typescript
import axios, { AxiosRequestConfig } from 'axios'
import { AUTH_TOKEN_KEY } from '../auth/AuthContext'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const axiosInstance = axios.create({
  baseURL: API_URL,
  withCredentials: true,
})

axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

function forceLogout(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY)
  window.location.href = '/'
}

axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status !== 401) {
      return Promise.reject(error)
    }

    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }

    if (originalRequest.url === '/auth/refresh' || originalRequest._retry) {
      forceLogout()
      return Promise.reject(error)
    }

    originalRequest._retry = true

    try {
      const { data } = await axiosInstance.post<{ token: string }>('/auth/refresh')
      localStorage.setItem(AUTH_TOKEN_KEY, data.token)
      if (originalRequest.headers) {
        originalRequest.headers.Authorization = `Bearer ${data.token}`
      }
      return axiosInstance(originalRequest)
    } catch {
      forceLogout()
      return Promise.reject(error)
    }
  },
)

export const customInstance = <T>(config: AxiosRequestConfig): Promise<T> =>
  axiosInstance(config).then(({ data }) => data as T)

export type ErrorType<Error> = Error
```

- [ ] **Step 2: Run the full frontend type check to verify no TS errors**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add withCredentials and 401 refresh interceptor to Axios client"
```

---

## Task 8: Fix React Query retry config

**Files:**
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Update `main.tsx` to not retry on 401**

Replace:
```typescript
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})
```

With:
```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (_, error) =>
        (error as { response?: { status?: number } })?.response?.status !== 401,
      staleTime: 30_000,
    },
  },
})
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/main.tsx
git commit -m "fix: skip React Query retry on 401 responses"
```

---

## Task 9: Update `AuthContext.tsx` — silent refresh on startup + logout API call

**Files:**
- Modify: `frontend/src/auth/AuthContext.tsx`

- [ ] **Step 1: Write failing tests in `frontend/src/auth/AuthContext.test.tsx`**

Replace the full contents of `frontend/src/auth/AuthContext.test.tsx`:

```typescript
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { AuthProvider, useAuth } from './AuthContext'

function makeJwt(expOffsetSeconds: number): string {
  const exp = Math.floor(Date.now() / 1000) + expOffsetSeconds
  const payload = btoa(JSON.stringify({ sub: 'u1', exp }))
  return `h.${payload}.s`
}

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
)

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('startup: no stored token', () => {
  it('attempts silent refresh, stays unauthenticated when it fails', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.isInitializing).toBe(true)
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.token).toBeNull()
  })
})

describe('startup: valid token in localStorage', () => {
  it('skips refresh and sets authenticated immediately', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const jwt = makeJwt(3600)
    localStorage.setItem('auth_token', jwt)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.token).toBe(jwt)
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('startup: expired token in localStorage', () => {
  it('silently refreshes and updates the token', async () => {
    localStorage.setItem('auth_token', makeJwt(-3600))
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ token: 'fresh-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    expect(result.current.token).toBe('fresh-token')
    expect(result.current.isAuthenticated).toBe(true)
    expect(localStorage.getItem('auth_token')).toBe('fresh-token')
  })

  it('clears stale token and stays unauthenticated when refresh fails', async () => {
    localStorage.setItem('auth_token', makeJwt(-3600))
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    expect(result.current.token).toBeNull()
    expect(localStorage.getItem('auth_token')).toBeNull()
  })
})

describe('login', () => {
  it('stores token in state and localStorage', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    act(() => result.current.login('my-token'))
    expect(result.current.token).toBe('my-token')
    expect(result.current.isAuthenticated).toBe(true)
    expect(localStorage.getItem('auth_token')).toBe('my-token')
  })
})

describe('logout', () => {
  it('clears token from state and localStorage', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    act(() => result.current.login('my-token'))
    act(() => result.current.logout())
    expect(result.current.token).toBeNull()
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('calls POST /auth/logout with credentials', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    act(() => result.current.login('my-token'))

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ message: 'logged out' }), { status: 200 }),
    )
    act(() => result.current.logout())

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/auth/logout'),
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd frontend && npx vitest run src/auth/AuthContext.test.tsx
```

Expected: multiple failures — `isInitializing` not in context, no silent refresh behavior.

- [ ] **Step 3: Replace the full contents of `frontend/src/auth/AuthContext.tsx`**

```typescript
import React, { createContext, useContext, useEffect, useState } from 'react'
import { API_URL } from '../api/client'

export const AUTH_TOKEN_KEY = 'auth_token'

interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  isInitializing: boolean
  login: (token: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1])) as { exp?: number }
    return payload.exp === undefined || Date.now() >= payload.exp * 1000
  } catch {
    return true
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem(AUTH_TOKEN_KEY),
  )
  const [isInitializing, setIsInitializing] = useState(true)

  useEffect(() => {
    const stored = localStorage.getItem(AUTH_TOKEN_KEY)
    if (stored && !isTokenExpired(stored)) {
      setIsInitializing(false)
      return
    }

    fetch(`${API_URL}/auth/refresh`, { method: 'POST', credentials: 'include' })
      .then((res) => {
        if (res.ok) return res.json() as Promise<{ token: string }>
        throw new Error('refresh failed')
      })
      .then(({ token: newToken }) => {
        localStorage.setItem(AUTH_TOKEN_KEY, newToken)
        setToken(newToken)
      })
      .catch(() => {
        localStorage.removeItem(AUTH_TOKEN_KEY)
        setToken(null)
      })
      .finally(() => setIsInitializing(false))
  }, [])

  const login = (t: string) => {
    localStorage.setItem(AUTH_TOKEN_KEY, t)
    setToken(t)
  }

  const logout = () => {
    fetch(`${API_URL}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {})
    localStorage.removeItem(AUTH_TOKEN_KEY)
    setToken(null)
  }

  return (
    <AuthContext.Provider value={{ token, isAuthenticated: !!token, isInitializing, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd frontend && npx vitest run src/auth/AuthContext.test.tsx
```

Expected: all `PASSED`

- [ ] **Step 5: Run the full frontend type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/auth/AuthContext.tsx frontend/src/auth/AuthContext.test.tsx
git commit -m "feat: add silent refresh on startup and API logout call to AuthContext"
```

---

## Task 10: Update `ProtectedRoute.tsx` to handle `isInitializing`

**Files:**
- Modify: `frontend/src/auth/ProtectedRoute.tsx`

- [ ] **Step 1: Update `ProtectedRoute` to show a loader while initializing**

Replace the full contents of `frontend/src/auth/ProtectedRoute.tsx`:

```typescript
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { useGetMe } from '../api/northlanding'

interface Props {
  requireAdmin?: boolean
}

export function ProtectedRoute({ requireAdmin = false }: Props) {
  const { isAuthenticated, isInitializing } = useAuth()
  const location = useLocation()

  if (isInitializing) return <div className="p-8 text-center">Loading…</div>

  if (!isAuthenticated) {
    return <Navigate to="/" state={{ from: location }} replace />
  }

  if (requireAdmin) {
    return <AdminGuard />
  }

  return <Outlet />
}

function AdminGuard() {
  const { data: user, isLoading, isError } = useGetMe()

  if (isLoading) return <div className="p-8 text-center">Loading…</div>
  if (isError) return <Navigate to="/" replace />
  if (!user?.is_admin) return <Navigate to="/my/discs" replace />

  return <Outlet />
}
```

- [ ] **Step 2: Run the full frontend test suite**

```bash
cd frontend && npx vitest run
```

Expected: all `PASSED` — no regressions.

- [ ] **Step 3: Run the full frontend type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/auth/ProtectedRoute.tsx
git commit -m "feat: show loading state in ProtectedRoute while auth initializes"
```

---

## Final verification

- [ ] **Run the complete backend test suite**

```bash
cd backend && pytest -v
```

Expected: all `PASSED`

- [ ] **Run the complete frontend test suite**

```bash
cd frontend && npx vitest run
```

Expected: all `PASSED`

- [ ] **Smoke test manually in the browser**

1. Start the backend: `cd backend && uvicorn app.main:app --reload`
2. Start the frontend: `cd frontend && npm run dev`
3. Log in via Google — confirm redirect works and the app loads
4. Open DevTools → Application → Cookies — confirm `refresh_token` cookie is set as httpOnly
5. Open DevTools → Application → Local Storage — confirm `auth_token` is present
6. Delete only the `auth_token` from localStorage (leave the cookie). Reload the page — confirm the app silently re-authenticates without redirecting to login
7. Click Logout — confirm `auth_token` is cleared, cookie is gone, and you land on the login page
8. Wait for the 60-minute access token to expire (or shorten `JWT_EXPIRE_MINUTES` temporarily for testing) — make an API call and confirm it auto-refreshes rather than hanging
