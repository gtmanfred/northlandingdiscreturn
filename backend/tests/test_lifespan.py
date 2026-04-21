import pytest
from unittest.mock import patch, MagicMock
from app.main import _ensure_storage_bucket


@pytest.mark.asyncio
async def test_skips_when_no_supabase_config(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with patch("app.main.get_storage_client") as mock_get:
        await _ensure_storage_bucket()
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_creates_disc_photos_bucket(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://storage:5000")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("SUPABASE_BUCKET", "disc-photos")
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


from app.repositories.user import UserRepository


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


async def test_get_by_emails_returns_empty_for_empty_list(db):
    repo = UserRepository(db)
    result = await repo.get_by_emails([])
    assert result == []
