from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from app.repositories.user import UserRepository
from app.routers.auth import _maybe_promote_to_admin
from app.services.auth import create_access_token, decode_access_token


def test_user_model_has_refresh_token_columns():
    from sqlalchemy import inspect
    from app.models.user import User
    mapper = inspect(User)
    cols = {c.key for c in mapper.attrs}
    assert "refresh_token" in cols
    assert "refresh_token_expires_at" in cols


def test_create_refresh_token_returns_64_char_hex():
    from app.services.auth import create_refresh_token
    token = create_refresh_token()
    assert len(token) == 64
    assert all(c in "0123456789abcdef" for c in token)


def test_create_refresh_token_is_unique():
    from app.services.auth import create_refresh_token
    assert create_refresh_token() != create_refresh_token()


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


async def test_create_and_decode_token():
    token = create_access_token("user-123")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"


async def test_get_current_user_invalid_token(client):
    response = await client.get("/users/me", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


async def test_get_current_user_no_token(client):
    response = await client.get("/users/me")
    assert response.status_code in (401, 403)  # HTTPBearer returns 403 or 401 when no credentials


async def test_maybe_promote_to_admin_promotes_seed_email(db):
    repo = UserRepository(db)
    user = await repo.create(name="Alice", email="alice@test.com", google_id="g-alice")
    with patch("app.routers.auth.settings") as mock_settings:
        mock_settings.ADMIN_EMAILS = ["alice@test.com"]
        await _maybe_promote_to_admin(user, "alice@test.com", repo, db)
    await db.refresh(user)
    assert user.is_admin is True


async def test_maybe_promote_to_admin_skips_non_seed_email(db):
    repo = UserRepository(db)
    user = await repo.create(name="Bob", email="bob@test.com", google_id="g-bob")
    with patch("app.routers.auth.settings") as mock_settings:
        mock_settings.ADMIN_EMAILS = ["seed@test.com"]
        await _maybe_promote_to_admin(user, "bob@test.com", repo, db)
    await db.refresh(user)
    assert user.is_admin is False


async def test_maybe_promote_to_admin_skips_already_admin(db):
    repo = UserRepository(db)
    user = await repo.create(name="Alice", email="alice@test.com", google_id="g-alice2")
    user.is_admin = True
    await db.flush()
    with patch("app.routers.auth.settings") as mock_settings:
        mock_settings.ADMIN_EMAILS = ["alice@test.com"]
        await _maybe_promote_to_admin(user, "alice@test.com", repo, db)
    assert user.is_admin is True
