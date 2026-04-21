# backend/tests/test_discs.py
import uuid
import pytest
from datetime import date
from unittest.mock import patch
from app.repositories.disc import DiscRepository
from app.repositories.user import UserRepository
from app.services.auth import create_access_token


async def test_create_disc(db):
    repo = DiscRepository(db)
    disc = await repo.create(
        manufacturer="Innova",
        name="Destroyer",
        color="Red",
        input_date=date.today(),
    )
    assert disc.id is not None
    assert disc.manufacturer == "Innova"
    assert disc.is_found is True
    assert disc.is_returned is False


async def test_list_all_discs(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="Discraft", name="Buzzz", color="Blue", input_date=date.today())
    await repo.create(manufacturer="Discraft", name="Zone", color="Green", input_date=date.today())
    discs = await repo.list_all()
    assert len(discs) == 2


async def test_list_discs_by_phone(db):
    repo = DiscRepository(db)
    await repo.create(
        manufacturer="MVP", name="Atom", color="Yellow",
        input_date=date.today(), phone_number="+15551111111"
    )
    await repo.create(manufacturer="MVP", name="Envy", color="Purple", input_date=date.today())
    discs = await repo.list_by_phone("+15551111111")
    assert len(discs) == 1
    assert discs[0].name == "Atom"


async def test_update_disc(db):
    repo = DiscRepository(db)
    disc = await repo.create(manufacturer="Latitude", name="Pure", color="White", input_date=date.today())
    updated = await repo.update(disc, is_returned=True, owner_name="Alice")
    assert updated.is_returned is True
    assert updated.owner_name == "Alice"


async def test_get_disc_by_id(db):
    repo = DiscRepository(db)
    disc = await repo.create(manufacturer="Dynamic", name="Lucid", color="Orange", input_date=date.today())
    found = await repo.get_by_id(disc.id)
    assert found is not None
    assert found.id == disc.id


async def test_delete_disc(db):
    repo = DiscRepository(db)
    disc = await repo.create(manufacturer="Prodigy", name="F5", color="Black", input_date=date.today())
    await repo.delete(disc.id)
    found = await repo.get_by_id(disc.id)
    assert found is None


async def test_add_and_delete_photo(db):
    repo = DiscRepository(db)
    disc = await repo.create(manufacturer="Innova", name="Wraith", color="Blue", input_date=date.today())
    photo = await repo.add_photo(disc.id, "discs/photo123.jpg", sort_order=0)
    assert photo.photo_path == "discs/photo123.jpg"
    returned_path = await repo.delete_photo(photo.id)
    assert returned_path == "discs/photo123.jpg"
    disc_reloaded = await repo.get_by_id(disc.id)
    assert len(disc_reloaded.photos) == 0


async def test_list_unreturned_found(db):
    repo = DiscRepository(db)
    # Should appear: found, not returned, has phone
    d1 = await repo.create(manufacturer="X", name="A", color="W", input_date=date.today(), phone_number="+15550000001")
    # Should NOT appear: is_returned=True
    d2 = await repo.create(manufacturer="X", name="B", color="W", input_date=date.today(), phone_number="+15550000002")
    await repo.update(d2, is_returned=True)
    # Should NOT appear: no phone number
    d3 = await repo.create(manufacturer="X", name="C", color="W", input_date=date.today())
    # Should NOT appear: is_found=False
    d4 = await repo.create(manufacturer="X", name="D", color="W", input_date=date.today(), phone_number="+15550000004", is_found=False)
    results = await repo.list_unreturned_found()
    result_ids = [r.id for r in results]
    assert d1.id in result_ids
    assert d2.id not in result_ids
    assert d3.id not in result_ids
    assert d4.id not in result_ids


async def test_list_by_phones(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="E", color="W", input_date=date.today(), phone_number="+15550000010")
    await repo.create(manufacturer="X", name="F", color="W", input_date=date.today(), phone_number="+15550000011")
    await repo.create(manufacturer="X", name="G", color="W", input_date=date.today(), phone_number="+15550000099")
    results = await repo.list_by_phones(["+15550000010", "+15550000011"])
    names = [r.name for r in results]
    assert "E" in names
    assert "F" in names
    assert "G" not in names


# --- Endpoint tests ---

def admin_headers(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


async def make_admin(db, name="Admin", email="admin@example.com", google_id="g-admin"):
    repo = UserRepository(db)
    user = await repo.create(name=name, email=email, google_id=google_id)
    user.is_admin = True
    await db.commit()
    return user


async def test_create_disc_as_admin(client, db):
    admin = await make_admin(db)
    resp = await client.post(
        "/discs",
        json={"manufacturer": "Innova", "name": "Destroyer", "color": "Red",
              "input_date": str(date.today()), "is_found": True},
        headers=admin_headers(admin.id),
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Destroyer"


async def test_create_disc_non_admin_forbidden(client, db):
    repo = UserRepository(db)
    user = await repo.create(name="Regular", email="reg@example.com", google_id="g-reg")
    await db.commit()
    resp = await client.post(
        "/discs",
        json={"manufacturer": "Innova", "name": "Boss", "color": "Blue",
              "input_date": str(date.today())},
        headers=admin_headers(user.id),
    )
    assert resp.status_code == 403


async def test_list_discs_admin_sees_all(client, db):
    admin = await make_admin(db, name="Admin2", email="admin2@example.com", google_id="g-admin2")
    resp = await client.get("/discs", headers=admin_headers(admin.id))
    assert resp.status_code == 200
    assert "items" in resp.json()


async def test_upload_photo(client, db):
    admin = await make_admin(db, name="Admin3", email="admin3@example.com", google_id="g-admin3")
    create_resp = await client.post(
        "/discs",
        json={"manufacturer": "MVP", "name": "Atom", "color": "Gold",
              "input_date": str(date.today())},
        headers=admin_headers(admin.id),
    )
    disc_id = create_resp.json()["id"]

    with patch("app.routers.discs.upload_photo", return_value=f"discs/{disc_id}/photo.jpg"):
        resp = await client.post(
            f"/discs/{disc_id}/photos",
            files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
            headers=admin_headers(admin.id),
        )
    assert resp.status_code == 201
