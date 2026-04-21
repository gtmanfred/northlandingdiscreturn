import uuid
from datetime import date
from app.repositories.disc import DiscRepository
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
    resp = await client.get("/suggestions?field=owner_name", headers=auth_headers(user.id))
    assert resp.status_code == 403


async def test_suggestions_owner_name_admin_succeeds(db, client):
    admin = await make_user(db, is_admin=True)
    disc_repo = DiscRepository(db)
    await disc_repo.create(manufacturer="Innova", name="Boss", color="Blue", input_date=date.today(), owner_name="Alice")
    await disc_repo.create(manufacturer="Discraft", name="Buzzz", color="Red", input_date=date.today(), owner_name="Bob")
    await disc_repo.create(manufacturer="MVP", name="Atom", color="Green", input_date=date.today(), owner_name="Alice")

    resp = await client.get("/suggestions?field=owner_name", headers=auth_headers(admin.id))
    assert resp.status_code == 200
    assert resp.json() == ["Alice", "Bob"]
