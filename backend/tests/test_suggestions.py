import uuid
from datetime import date
from app.repositories.disc import DiscRepository
from app.repositories.owner import OwnerRepository
from app.repositories.user import UserRepository
from app.services.auth import create_access_token


def auth_headers(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


async def make_user(db, *, is_admin=False):
    repo = UserRepository(db)
    user = await repo.create(
        name="Test User",
        email=f"user-{uuid.uuid4()}@example.com",
        google_id=str(uuid.uuid4()),
    )
    if is_admin:
        user.is_admin = True
        await db.flush()
    return user


async def test_suggestions_manufacturer_returns_distinct_sorted(db, client):
    user = await make_user(db)
    disc_repo = DiscRepository(db)
    await disc_repo.create(manufacturer="Innova", name="Boss", color="Blue", input_date=date.today())
    await disc_repo.create(manufacturer="Discraft", name="Buzzz", color="Red", input_date=date.today())
    await disc_repo.create(manufacturer="Innova", name="Wraith", color="Green", input_date=date.today())

    resp = await client.get("/suggestions?field=manufacturer", headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.json() == ["Discraft", "Innova"]


async def test_suggestions_requires_auth(client):
    resp = await client.get("/suggestions?field=manufacturer")
    assert resp.status_code == 401


async def test_suggestions_color(db, client):
    user = await make_user(db)
    disc_repo = DiscRepository(db)
    await disc_repo.create(manufacturer="Innova", name="Boss", color="Blue", input_date=date.today())
    await disc_repo.create(manufacturer="Innova", name="Wraith", color="Blue", input_date=date.today())
    await disc_repo.create(manufacturer="Discraft", name="Buzzz", color="Red", input_date=date.today())

    resp = await client.get("/suggestions?field=color", headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.json() == ["Blue", "Red"]


async def test_suggestions_owner_name_requires_admin(db, client):
    user = await make_user(db, is_admin=False)
    resp = await client.get("/suggestions?field=owner_first_name", headers=auth_headers(user.id))
    assert resp.status_code == 403


async def test_suggestions_owner_name_admin_succeeds(db, client):
    admin = await make_user(db, is_admin=True)
    owner_repo = OwnerRepository(db)
    await owner_repo.resolve_or_create(first_name="Alice", last_name="", phone_number="+15551110001")
    await owner_repo.resolve_or_create(first_name="Bob", last_name="", phone_number="+15552220001")
    # Duplicate first_name — should appear only once
    await owner_repo.resolve_or_create(first_name="Alice", last_name="", phone_number="+15551110002")

    resp = await client.get("/suggestions?field=owner_first_name", headers=auth_headers(admin.id))
    assert resp.status_code == 200
    assert resp.json() == ["Alice", "Bob"]


async def test_phone_suggestions_requires_admin(db, client):
    user = await make_user(db, is_admin=False)
    resp = await client.get("/suggestions/phone?owner_first_name=Alice&owner_last_name=", headers=auth_headers(user.id))
    assert resp.status_code == 403


async def test_phone_suggestions_from_disc_records(db, client):
    admin = await make_user(db, is_admin=True)
    owner_repo = OwnerRepository(db)
    await owner_repo.resolve_or_create(first_name="Alice", last_name="", phone_number="+15551112222")
    await owner_repo.resolve_or_create(first_name="Alice", last_name="", phone_number="+15553334444")
    await owner_repo.resolve_or_create(first_name="Bob", last_name="", phone_number="+15559998888")

    resp = await client.get("/suggestions/phone?owner_first_name=Alice&owner_last_name=", headers=auth_headers(admin.id))
    assert resp.status_code == 200
    data = resp.json()
    numbers = [s["number"] for s in data]
    assert "+15551112222" in numbers
    assert "+15553334444" in numbers
    assert "+15559998888" not in numbers


async def test_phone_suggestions_from_registered_users(db, client):
    admin = await make_user(db, is_admin=True)
    user_repo = UserRepository(db)
    owner = await user_repo.create(name="Alice", email="alice@example.com", google_id="google-alice-99")
    phone = await user_repo.add_phone_number(owner.id, "+15550001111")
    await user_repo.verify_phone(phone.id)

    resp = await client.get("/suggestions/phone?owner_first_name=Alice&owner_last_name=", headers=auth_headers(admin.id))
    assert resp.status_code == 200
    data = resp.json()
    assert any(s["number"] == "+15550001111" and "alice@example.com" in s["label"] for s in data)


async def test_phone_suggestions_deduplicates_registered_wins(db, client):
    admin = await make_user(db, is_admin=True)
    user_repo = UserRepository(db)
    owner_repo = OwnerRepository(db)

    owner = await user_repo.create(name="Alice", email="alice@example.com", google_id="google-alice-dedup")
    phone = await user_repo.add_phone_number(owner.id, "+15550001111")
    await user_repo.verify_phone(phone.id)

    # Same phone number also in owners table
    await owner_repo.resolve_or_create(first_name="Alice", last_name="", phone_number="+15550001111")

    resp = await client.get("/suggestions/phone?owner_first_name=Alice&owner_last_name=", headers=auth_headers(admin.id))
    assert resp.status_code == 200
    data = resp.json()
    matching = [s for s in data if s["number"] == "+15550001111"]
    assert len(matching) == 1
    assert "alice@example.com" in matching[0]["label"]


async def test_phone_suggestions_requires_auth(client):
    resp = await client.get("/suggestions/phone?owner_first_name=Alice&owner_last_name=")
    assert resp.status_code == 401


async def test_phone_suggestions_empty_owner_name_rejected(db, client):
    admin = await make_user(db, is_admin=True)
    # Both first and last name empty — should return empty list (not 422)
    resp = await client.get("/suggestions/phone", headers=auth_headers(admin.id))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_phone_suggestions_case_insensitive(db, client):
    admin = await make_user(db, is_admin=True)
    user_repo = UserRepository(db)
    owner = await user_repo.create(name="Alice Smith", email="alice.smith@example.com", google_id="google-alice-ci")
    phone = await user_repo.add_phone_number(owner.id, "+15556667777")
    await user_repo.verify_phone(phone.id)

    resp = await client.get("/suggestions/phone?owner_first_name=alice+smith&owner_last_name=", headers=auth_headers(admin.id))
    assert resp.status_code == 200
    data = resp.json()
    assert any(s["number"] == "+15556667777" for s in data)
