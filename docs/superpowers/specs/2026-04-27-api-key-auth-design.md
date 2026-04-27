# API Key Authentication

## Goal

Allow users to generate a personal API key so they can call the Houston API
without going through Google OAuth2. The key is shown to the user once at
creation time; only a salted hash is stored.

## Scope

- One API key per user (regenerating replaces the existing key).
- Keys never expire; users revoke or regenerate explicitly.
- Keys work everywhere the JWT bearer works — same `get_current_user`
  dependency, including admin-only endpoints.
- New endpoints to create/view-metadata/revoke a key.
- Config and example/test stack updates for the new HMAC secret.

Out of scope: multiple keys per user, labels, expiration, scoped permissions.

## Crypto

- **Plaintext format:** `hou_<token>`, where `<token>` is
  `secrets.token_urlsafe(32)` (≈43 url-safe base64 chars, 256 bits of entropy).
- **Hashing:** `hmac.new(secret.encode(), plaintext.encode(), sha256).hexdigest()`.
  Deterministic so we can look up by hash with a single indexed query.
- **Server secret:** `API_KEY_HMAC_SECRET`, sourced from env. No default —
  app must fail to start in production if unset. Tests/examples use a
  placeholder value.

The plaintext API key has 256 bits of entropy, so a per-row salt is not
required — a single server-side HMAC secret is sufficient and lets us look up
keys directly by hash.

## Data model

New table `api_keys`:

| column        | type        | notes                                |
|---------------|-------------|--------------------------------------|
| `id`          | UUID PK     |                                      |
| `user_id`     | UUID        | FK → `users.id`, **unique**, ON DELETE CASCADE |
| `key_hash`    | text        | unique, indexed (hex HMAC-SHA256)    |
| `last_four`   | char(4)     | last 4 chars of plaintext token; shown in UI |
| `created_at`  | timestamptz | server default `now()`               |
| `last_used_at`| timestamptz | nullable                             |

Alembic migration adds the table.

## Helper module

`app/auth/api_key.py`:

- `API_KEY_PREFIX = "hou_"`
- `generate_api_key() -> tuple[str, str, str]` → returns
  `(plaintext, key_hash, last_four)`.
- `hash_api_key(plaintext: str) -> str` — uses `settings.API_KEY_HMAC_SECRET`.
- `looks_like_api_key(token: str) -> bool` — checks the prefix.

Both the router and the auth dependency import from this module so there is
one implementation of hashing.

## Auth dependency change

`app/deps.py::get_current_user`:

1. Extract bearer token (existing behavior).
2. If `looks_like_api_key(token)`:
   - Hash it, look up `api_keys` row by `key_hash`.
   - If found, load the associated `User`, update `last_used_at` (best-effort
     — failures here must not block the request), return the user.
   - If not found, raise 401.
3. Otherwise, fall through to the existing JWT decode path.

`require_admin` is unchanged — it wraps `get_current_user` so admin endpoints
work transparently with API keys for admin users.

## Endpoints

All under a new router `app/routers/api_keys.py`, mounted at
`/users/me/api-key`. All require `get_current_user`.

- **`POST /users/me/api-key`** — generate (or regenerate) a key.
  - Generates plaintext + hash + last_four.
  - Deletes any existing row for the user, inserts new row.
  - Response: `{ "api_key": "hou_…", "last_four": "abcd", "created_at": "…" }`.
  - This is the only place the plaintext is ever returned.
- **`GET /users/me/api-key`** — metadata.
  - 200 with `{ "last_four", "created_at", "last_used_at" }` if a key exists.
  - 404 if no key.
- **`DELETE /users/me/api-key`** — revoke.
  - 204 on success; 404 if no key.

These endpoints themselves require JWT authentication in practice (a request
authenticated by an API key can also call them — that's fine, it lets a
client rotate its own key).

## Config

`app/config.py` adds:

```python
API_KEY_HMAC_SECRET: str = ""
```

(Default empty, like other secrets in this file.) The auth helper raises a
clear error if it's empty when used at runtime, so production deploys without
the env var fail fast.

## Config / stack updates

- `backend/.env.example`: add `API_KEY_HMAC_SECRET=replace-with-random-secret`.
- `.env.example` (root): add `API_KEY_HMAC_SECRET=`.
- `docker-compose.yml`: pass `API_KEY_HMAC_SECRET: ${API_KEY_HMAC_SECRET}` into
  the backend service alongside `SECRET_KEY`.
- `backend/teststack.toml`: add
  `API_KEY_HMAC_SECRET = "test-api-key-hmac-secret"`.

## Tests

New file `backend/tests/test_api_keys.py`:

- `POST` returns plaintext that starts with `hou_` and matches `last_four`.
- Calling `POST` twice replaces the existing key (old key no longer
  authenticates; new key does).
- `GET` returns metadata only and never the plaintext; 404 when no key.
- `DELETE` removes the key; subsequent calls with the old key return 401.
- Authenticating to a representative protected endpoint (e.g. `/users/me`)
  works with `Authorization: Bearer hou_…`.
- Invalid API key returns 401.
- Existing JWT auth still works (regression).
- `last_used_at` is updated on a successful API-key-authenticated request.

## Frontend

Out of scope for this spec — the backend exposes the endpoints; UI for
managing keys can be added in a follow-up. The `last_four` field is included
specifically so a future UI can show "your key ending in `abcd`".
