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

    resp2 = await client.delete("/users/me/api-key", headers=jwt_headers(user.id))
    assert resp2.status_code == 404


async def test_endpoints_require_authentication(client):
    assert (await client.post("/users/me/api-key")).status_code == 401
    assert (await client.get("/users/me/api-key")).status_code == 401
    assert (await client.delete("/users/me/api-key")).status_code == 401
