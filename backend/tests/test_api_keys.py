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
    monkeypatch.setenv("API_KEY_HMAC_SECRET", "")
    with pytest.raises(RuntimeError):
        hash_api_key("hou_anything")


def test_looks_like_api_key():
    assert looks_like_api_key("hou_abc")
    assert not looks_like_api_key("eyJhbGciOi...")
    assert not looks_like_api_key("")


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
