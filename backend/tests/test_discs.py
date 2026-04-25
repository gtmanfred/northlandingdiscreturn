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
    from app.repositories.owner import OwnerRepository
    owner_repo = OwnerRepository(db)
    owner = await owner_repo.resolve_or_create(name="Atom Owner", phone_number="+15551111111")
    await db.flush()
    repo = DiscRepository(db)
    await repo.create(
        manufacturer="MVP", name="Atom", color="Yellow",
        input_date=date.today(), owner_id=owner.id,
    )
    await repo.create(manufacturer="MVP", name="Envy", color="Purple", input_date=date.today())
    owners = await owner_repo.list_by_phones(["+15551111111"])
    discs = await repo.list_by_owner_ids([o.id for o in owners])
    assert len(discs) == 1
    assert discs[0].name == "Atom"


async def test_update_disc(db):
    repo = DiscRepository(db)
    disc = await repo.create(manufacturer="Latitude", name="Pure", color="White", input_date=date.today())
    updated = await repo.update(disc, is_returned=True)
    assert updated.is_returned is True


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
    from app.repositories.owner import OwnerRepository
    owner_repo = OwnerRepository(db)
    o1 = await owner_repo.resolve_or_create(name="OA", phone_number="+15550000001")
    o2 = await owner_repo.resolve_or_create(name="OB", phone_number="+15550000002")
    o4 = await owner_repo.resolve_or_create(name="OD", phone_number="+15550000004")
    await db.flush()
    repo = DiscRepository(db)
    # Should appear: found, not returned, has owner
    d1 = await repo.create(manufacturer="X", name="A", color="W", input_date=date.today(), owner_id=o1.id)
    # Should NOT appear: is_returned=True
    d2 = await repo.create(manufacturer="X", name="B", color="W", input_date=date.today(), owner_id=o2.id)
    await repo.update(d2, is_returned=True)
    # Should NOT appear: no owner
    d3 = await repo.create(manufacturer="X", name="C", color="W", input_date=date.today())
    # Should NOT appear: is_found=False
    d4 = await repo.create(manufacturer="X", name="D", color="W", input_date=date.today(), owner_id=o4.id, is_found=False)
    results = await repo.list_unreturned_found()
    result_ids = [r.id for r in results]
    assert d1.id in result_ids
    assert d2.id not in result_ids
    assert d3.id not in result_ids
    assert d4.id not in result_ids


async def test_list_by_phones(db):
    from app.repositories.owner import OwnerRepository
    owner_repo = OwnerRepository(db)
    oE = await owner_repo.resolve_or_create(name="OE", phone_number="+15550000010")
    oF = await owner_repo.resolve_or_create(name="OF", phone_number="+15550000011")
    oG = await owner_repo.resolve_or_create(name="OG", phone_number="+15550000099")
    await db.flush()
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="E", color="W", input_date=date.today(), owner_id=oE.id)
    await repo.create(manufacturer="X", name="F", color="W", input_date=date.today(), owner_id=oF.id)
    await repo.create(manufacturer="X", name="G", color="W", input_date=date.today(), owner_id=oG.id)
    owners = await owner_repo.list_by_phones(["+15550000010", "+15550000011"])
    results = await repo.list_by_owner_ids([o.id for o in owners])
    names = [r.name for r in results]
    assert "E" in names
    assert "F" in names
    assert "G" not in names


async def test_list_all_is_found_true(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="Found", color="W", input_date=date.today(), is_found=True)
    await repo.create(manufacturer="X", name="Wishlist", color="W", input_date=date.today(), is_found=False)
    results = await repo.list_all(is_found=True)
    assert all(d.is_found is True for d in results)
    names = [d.name for d in results]
    assert "Found" in names
    assert "Wishlist" not in names


async def test_list_all_is_found_false(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="Found2", color="W", input_date=date.today(), is_found=True)
    await repo.create(manufacturer="X", name="Wishlist2", color="W", input_date=date.today(), is_found=False)
    results = await repo.list_all(is_found=False)
    assert all(d.is_found is False for d in results)
    names = [d.name for d in results]
    assert "Wishlist2" in names
    assert "Found2" not in names


async def test_list_all_owner_name_filter(db):
    from app.repositories.owner import OwnerRepository
    owner_repo = OwnerRepository(db)
    oA = await owner_repo.resolve_or_create(name="Alice Smith", phone_number="+15550001001")
    oB = await owner_repo.resolve_or_create(name="Bob Jones", phone_number="+15550001002")
    await db.flush()
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="D1", color="W", input_date=date.today(), owner_id=oA.id)
    await repo.create(manufacturer="X", name="D2", color="W", input_date=date.today(), owner_id=oB.id)
    results = await repo.list_all(owner_name="alice")
    names = [d.name for d in results]
    assert "D1" in names
    assert "D2" not in names


async def test_list_all_combined_filters(db):
    from app.repositories.owner import OwnerRepository
    owner_repo = OwnerRepository(db)
    oC = await owner_repo.resolve_or_create(name="Carol", phone_number="+15550002001")
    oD = await owner_repo.resolve_or_create(name="Dave", phone_number="+15550002002")
    await db.flush()
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="Match", color="W", input_date=date.today(), is_found=True, owner_id=oC.id)
    await repo.create(manufacturer="X", name="WrongOwner", color="W", input_date=date.today(), is_found=True, owner_id=oD.id)
    await repo.create(manufacturer="X", name="WrongFound", color="W", input_date=date.today(), is_found=False, owner_id=oC.id)
    results = await repo.list_all(is_found=True, owner_name="carol")
    names = [d.name for d in results]
    assert "Match" in names
    assert "WrongOwner" not in names
    assert "WrongFound" not in names


async def test_count_all_with_is_found_filter(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="F1", color="W", input_date=date.today(), is_found=True)
    await repo.create(manufacturer="X", name="F2", color="W", input_date=date.today(), is_found=True)
    await repo.create(manufacturer="X", name="W1", color="W", input_date=date.today(), is_found=False)
    assert await repo.count_all(is_found=True) == 2
    assert await repo.count_all(is_found=False) == 1
    assert await repo.count_all() == 3


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


async def test_admin_list_discs_is_found_filter(client, db):
    admin = await make_admin(db, name="Admin4", email="admin4@example.com", google_id="g-admin4")
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="FoundDisc", color="W", input_date=date.today(), is_found=True)
    await repo.create(manufacturer="X", name="WishlistDisc", color="W", input_date=date.today(), is_found=False)
    await db.commit()

    resp = await client.get("/discs?is_found=true", headers=admin_headers(admin.id))
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()["items"]]
    assert "FoundDisc" in names
    assert "WishlistDisc" not in names

    resp2 = await client.get("/discs?is_found=false", headers=admin_headers(admin.id))
    assert resp2.status_code == 200
    names2 = [d["name"] for d in resp2.json()["items"]]
    assert "WishlistDisc" in names2
    assert "FoundDisc" not in names2


async def test_admin_list_discs_owner_name_filter(client, db):
    from app.repositories.owner import OwnerRepository
    admin = await make_admin(db, name="Admin5", email="admin5@example.com", google_id="g-admin5")
    owner_repo = OwnerRepository(db)
    oA = await owner_repo.resolve_or_create(name="Alice", phone_number="+15550003001")
    oB = await owner_repo.resolve_or_create(name="Bob", phone_number="+15550003002")
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="AliceDisc", color="W", input_date=date.today(), owner_id=oA.id)
    await repo.create(manufacturer="X", name="BobDisc", color="W", input_date=date.today(), owner_id=oB.id)
    await db.commit()

    resp = await client.get("/discs?owner_name=alice", headers=admin_headers(admin.id))
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()["items"]]
    assert "AliceDisc" in names
    assert "BobDisc" not in names


async def test_non_admin_ignores_filter_params(client, db):
    user_repo = UserRepository(db)
    user = await user_repo.create(name="Regular2", email="reg2@example.com", google_id="g-reg2")
    await db.commit()

    # Non-admin with is_found filter — should 200 (params silently ignored, returns their discs)
    resp = await client.get("/discs?is_found=false", headers=admin_headers(user.id))
    assert resp.status_code == 200


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


async def test_admin_create_disc_enqueues_heads_up(db, client):
    from sqlalchemy import select
    from app.models.pickup_event import SMSJob
    from app.models.owner import Owner

    admin = await make_admin(db)
    resp = await client.post(
        "/discs",
        headers=admin_headers(admin.id),
        json={
            "manufacturer": "Innova",
            "name": "Destroyer",
            "color": "red",
            "input_date": "2026-04-01",
            "owner_name": "New Owner",
            "phone_number": "5551234567",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["owner"]["name"] == "New Owner"
    assert body["owner"]["phone_number"] == "+15551234567"

    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert len(jobs) == 1
    assert "New Owner" in jobs[0].message

    owner = (await db.execute(select(Owner))).scalar_one()
    assert owner.heads_up_sent_at is not None


async def test_admin_create_second_disc_same_owner_skips_heads_up(db, client):
    from sqlalchemy import select
    from app.models.pickup_event import SMSJob

    admin = await make_admin(db)
    for _ in range(2):
        resp = await client.post(
            "/discs",
            headers=admin_headers(admin.id),
            json={
                "manufacturer": "Innova",
                "name": "Destroyer",
                "color": "red",
                "input_date": "2026-04-01",
                "owner_name": "Repeat Owner",
                "phone_number": "5557778888",
            },
        )
        assert resp.status_code == 201

    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert len(jobs) == 1
