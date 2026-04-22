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
