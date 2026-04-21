# Seed Admins via Environment Variable — Design

**Goal:** Allow operators to declare admin users by email in an environment variable; matching users are promoted to admin on startup, and seed admins cannot be demoted via the API.

**Architecture:** Add an `ADMIN_EMAILS` env var (CSV) to the config, parsed into a list using a figenv coerce class. The lifespan function queries the DB for matching users and sets `is_admin = True`. The existing `PATCH /admin/users/{user_id}` endpoint rejects demotion of seed admin emails.

**Tech Stack:** FastAPI, figenv, SQLAlchemy async, existing `User` model (`is_admin` boolean), existing `PATCH /admin/users/{user_id}` endpoint.

---

## Config

Add a `csv` coerce class and `ADMIN_EMAILS` field to `app/config.py`:

```python
class csv:
    @staticmethod
    def _coerce(value):
        return [v.strip() for v in value.split(",") if v.strip()]

class Config(metaclass=figenv.MetaConfig):
    # ... existing fields ...
    ADMIN_EMAILS: csv = ""
```

`Config.ADMIN_EMAILS` returns a `list[str]`. Empty string (default) → empty list, feature disabled.

---

## Startup Promotion

In `app/main.py`, the `lifespan` function gains a second startup step after `_ensure_storage_bucket()`:

```python
async def _promote_seed_admins() -> None:
    emails = settings.ADMIN_EMAILS
    if not emails:
        return
    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        users = await repo.get_by_emails(emails)
        for user in users:
            if not user.is_admin:
                await repo.update(user, is_admin=True)
        await db.commit()
```

- Uses `AsyncSessionLocal` from `app/database.py` directly (not the FastAPI `get_db` dependency).
- Skips entirely when `ADMIN_EMAILS` is empty.
- Only updates users already in the DB (users who haven't logged in yet are promoted when they first authenticate — see Auth section below).
- Only touches users where `is_admin` is currently `False` (idempotent).
- Requires a new `UserRepository.get_by_emails(emails: list[str]) -> list[User]` method using a SQL `WHERE email IN (...)` query.

---

## Auth-time Promotion

In the Google OAuth callback (`app/routers/auth.py`), after a user record is created or fetched, check if their email is in `ADMIN_EMAILS` and set `is_admin = True` if not already set. This ensures seed admins are promoted even if they sign in after the server starts.

---

## Demotion Guard

In `PATCH /admin/users/{user_id}` (`app/routers/admin.py`), add a check before committing:

```python
if body.is_admin is False and user.email in settings.ADMIN_EMAILS:
    raise HTTPException(status_code=403, detail="Cannot demote a seed admin")
```

Any admin can call this endpoint, but seed admin emails are protected from demotion.

---

## Environment

Add to `.env.example`:

```
# Comma-separated list of emails that are always admins (promoted on startup)
ADMIN_EMAILS=
```

Add to `docker-compose.yml` backend environment:

```yaml
ADMIN_EMAILS: ${ADMIN_EMAILS:-}
```

---

## Testing

- `test_config.py`: `ADMIN_EMAILS` parses CSV → list; empty string → empty list.
- `test_lifespan.py`: startup promotes matching users; skips already-admin users; skips when env var empty; does not demote admins not in list.
- `test_auth.py`: OAuth callback promotes user if email in `ADMIN_EMAILS`.
- `test_admin.py`: `PATCH /admin/users/{id}` with `is_admin=false` on seed admin → 403; on non-seed admin → 200.
