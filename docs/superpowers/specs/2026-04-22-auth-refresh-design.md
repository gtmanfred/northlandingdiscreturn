# Auth Auto-Logout & Refresh Token Design

**Date:** 2026-04-22
**Status:** Approved

## Problem

When a user's 60-minute JWT expires, the frontend has no mechanism to detect this. `isAuthenticated` stays `true` (it's just a truthy check on a localStorage string), API calls silently return 401, React Query retries them once, and the user is left stuck on a broken page with no logout or redirect.

Additionally, users must re-authenticate via Google every 60 minutes, which is disruptive.

## Solution

Approach B: short-lived access token (60 min, unchanged) + long-lived refresh token (30 days, stored in an httpOnly cookie). The frontend silently exchanges a valid refresh cookie for a new access token rather than forcing a Google re-auth.

---

## Backend

### Data Model

Add two nullable columns to the `users` table via Alembic migration:

| Column | Type | Description |
|--------|------|-------------|
| `refresh_token` | `String`, unique, nullable | Cryptographically random 32-byte hex string |
| `refresh_token_expires_at` | `DateTime(timezone=True)`, nullable | UTC expiry, 30 days from issuance |

The refresh token is an opaque random string (not a JWT) so it can be revoked by clearing the DB row.

### Token Issuance — Google Callback Update

After issuing the 60-minute access JWT (unchanged), the callback also:
1. Generates a new refresh token: `secrets.token_hex(32)`
2. Writes `refresh_token` and `refresh_token_expires_at = now() + 30 days` to the user row
3. Sets `Set-Cookie: refresh_token=<value>; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000` on the redirect response

### `POST /auth/refresh` (new endpoint)

1. Read `refresh_token` cookie from request
2. Look up user: `WHERE users.refresh_token = <cookie_value>`
3. If not found → 401
4. If `refresh_token_expires_at < utcnow()` → 401
5. Issue new 60-minute access JWT
6. **Rotate** the refresh token: generate new random token, update DB, set new cookie with fresh `Max-Age=2592000`
7. Return `{ "token": "<new_access_jwt>" }`

Rotation ensures each use of a refresh token invalidates the previous one, limiting the blast radius of a stolen token.

### `POST /auth/logout` (updated — currently a no-op)

1. Read `refresh_token` cookie — if missing, skip DB step and go to step 3
2. Find user by `WHERE users.refresh_token = <cookie_value>` — if not found, skip to step 3 (graceful no-op)
3. Set `refresh_token = null`, `refresh_token_expires_at = null` on the matching user row
4. Set `Set-Cookie: refresh_token=; HttpOnly; Secure; SameSite=Lax; Max-Age=0` to expire the cookie
5. Return `{ "message": "logged out" }`

### CORS Update

In `main.py`, update the CORS middleware:
- `allow_credentials=True`
- `allow_origins=[settings.FRONTEND_URL]` (explicit origin required when credentials are enabled — `*` is not permitted)

---

## Frontend

### `client.ts` — Axios Configuration

- Add `withCredentials: true` to the Axios instance so the browser sends the `refresh_token` cookie on backend requests.

### `client.ts` — Response Interceptor (new)

`client.ts` lives outside the React tree and cannot call `AuthContext.logout()` directly. For the force-logout path (refresh token rejected), the interceptor manages auth state itself: it clears localStorage and redirects. It does not call `POST /auth/logout` in this path — the refresh token is already invalid so there is nothing to revoke server-side.

```
on 401 response:
  if the failing request is POST /auth/refresh → force logout (avoid infinite loop):
    localStorage.removeItem('auth_token')
    window.location.href = '/'
  else:
    call POST /auth/refresh (with credentials)
    if success:
      store new token in localStorage
      retry original request with new Authorization header
    if failure (401 from /auth/refresh):
      localStorage.removeItem('auth_token')
      window.location.href = '/'
```

The explicit user logout (Navbar button) still calls `AuthContext.logout()`, which calls `POST /auth/logout` to revoke the refresh token and expire the cookie before clearing local state.

### `AuthContext.tsx` — Silent Refresh on Startup

Replace the current "initialize from localStorage, no validation" mount logic with:

```
on mount:
  set loading = true
  if token in localStorage AND exp claim > now():
    // token is valid, proceed
  else:
    call POST /auth/refresh
    if success:
      store new token in localStorage + state
    if failure:
      clear any stale token from localStorage
      set token = null
  set loading = false
```

Show a loading state while this check runs to prevent the login page from flashing momentarily for users with a valid refresh cookie.

### `AuthContext.tsx` — `logout()` Update

```
async logout():
  fire-and-forget POST /auth/logout  // clears DB + expires cookie
  remove auth_token from localStorage
  set token state = null
```

Fire-and-forget: do not block logout on the network call succeeding. If the backend is unreachable, the user is still logged out locally; the refresh cookie will be rejected by the backend on next use anyway.

### `main.tsx` — React Query Retry Fix

Change the global QueryClient retry config from `retry: 1` to:
```ts
retry: (failureCount, error) => error?.response?.status !== 401
```

This prevents React Query from retrying 401 failures — the Axios interceptor handles them, and retrying would send a second request with the same expired token before the interceptor has a chance to refresh.

---

## Error Handling & Edge Cases

| Scenario | Behavior |
|----------|----------|
| User clears cookies manually | Next API call returns 401 → interceptor tries refresh → 401 again → logout() clears stale localStorage token |
| Admin deletes refresh token from DB | Next refresh returns 401 → interceptor calls logout() → user is sent to login |
| Multiple browser tabs | Cookie is shared by browser; when one tab rotates the token, other tabs with old access tokens will 401, hit the interceptor, and refresh successfully using the shared cookie |
| Backend unreachable on startup | Silent refresh fails → user sees login page; local token (if expired) is cleared |
| Refresh token older than 30 days | `/auth/refresh` returns 401 → user must re-authenticate via Google |
| Stolen access token used | Token expires in ≤60 min with no renewal path for the attacker (they don't have the httpOnly cookie) |
| Stolen refresh token used | Rotation invalidates the attacker's copy on first use; the legitimate user's next refresh fails → they are logged out and re-authenticate, generating a new refresh token |

---

## Files Changed

### Backend
- `backend/app/models/user.py` — add `refresh_token`, `refresh_token_expires_at` columns
- `backend/alembic/versions/<new>.py` — migration adding the two columns
- `backend/app/services/auth.py` — add `create_refresh_token()`, update `create_access_token` call site
- `backend/app/routers/auth.py` — update `googleCallback` to set cookie; add `POST /auth/refresh`; update `POST /auth/logout` to clear DB + cookie
- `backend/app/main.py` — update CORS `allow_credentials` and `allow_origins`

### Frontend
- `frontend/src/api/client.ts` — add `withCredentials: true`, add 401 response interceptor
- `frontend/src/auth/AuthContext.tsx` — add startup silent refresh, add loading state, update `logout()` to call API
- `frontend/src/main.tsx` — update React Query retry config
