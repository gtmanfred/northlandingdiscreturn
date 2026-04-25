# backend/tests/test_users.py
import uuid
from unittest.mock import patch
import pytest
from datetime import date
from app.repositories.user import UserRepository
from app.repositories.disc import DiscRepository
from app.repositories.owner import OwnerRepository
from app.services.auth import create_access_token


async def test_create_user(db):
    repo = UserRepository(db)
    user = await repo.create(
        name="Alice", email="alice@example.com", google_id="google-123"
    )
    assert user.id is not None
    assert user.email == "alice@example.com"
    assert user.is_admin is False


async def test_get_by_email(db):
    repo = UserRepository(db)
    await repo.create(name="Bob", email="bob@example.com", google_id="google-bob")
    found = await repo.get_by_email("bob@example.com")
    assert found is not None
    assert found.name == "Bob"


async def test_get_by_google_id(db):
    repo = UserRepository(db)
    await repo.create(name="Carol", email="carol@example.com", google_id="google-carol")
    found = await repo.get_by_google_id("google-carol")
    assert found is not None
    assert found.email == "carol@example.com"


async def test_add_phone_number(db):
    repo = UserRepository(db)
    user = await repo.create(name="Dave", email="dave@example.com", google_id="google-dave")
    phone = await repo.add_phone_number(user.id, "+15551234567")
    assert phone.number == "+15551234567"
    assert phone.verified is False


async def test_verify_phone_number(db):
    repo = UserRepository(db)
    user = await repo.create(name="Eve", email="eve@example.com", google_id="google-eve")
    phone = await repo.add_phone_number(user.id, "+15559876543")
    updated = await repo.verify_phone(phone.id)
    assert updated.verified is True
    assert updated.verified_at is not None


async def test_get_verified_numbers_for_user(db):
    repo = UserRepository(db)
    user = await repo.create(name="Frank", email="frank@example.com", google_id="google-frank")
    p1 = await repo.add_phone_number(user.id, "+15550001111")
    await repo.verify_phone(p1.id)
    await repo.add_phone_number(user.id, "+15550002222")  # unverified
    numbers = await repo.get_verified_numbers(user.id)
    assert len(numbers) == 1
    assert numbers[0].number == "+15550001111"


async def test_update_user(db):
    repo = UserRepository(db)
    user = await repo.create(name="Grace", email="grace@example.com", google_id="google-grace")
    updated = await repo.update(user, name="Grace Updated", is_admin=True)
    assert updated.name == "Grace Updated"
    assert updated.is_admin is True


async def test_set_verification_code(db):
    repo = UserRepository(db)
    user = await repo.create(name="Hank", email="hank@example.com", google_id="google-hank")
    phone = await repo.add_phone_number(user.id, "+15551112222")
    updated = await repo.set_verification_code(phone.id, "123456")
    assert updated.verification_code == "123456"
    assert updated.verification_expires_at is not None


async def test_get_phone_by_number(db):
    repo = UserRepository(db)
    user = await repo.create(name="Iris", email="iris@example.com", google_id="google-iris")
    await repo.add_phone_number(user.id, "+15553334444")
    found = await repo.get_phone_by_number(user.id, "+15553334444")
    assert found is not None
    assert found.number == "+15553334444"
    missing = await repo.get_phone_by_number(user.id, "+19999999999")
    assert missing is None


async def test_delete_phone(db):
    repo = UserRepository(db)
    user = await repo.create(name="Jake", email="jake@example.com", google_id="google-jake")
    phone = await repo.add_phone_number(user.id, "+15555556666")
    await repo.delete_phone(phone.id)
    gone = await repo.get_phone_by_number(user.id, "+15555556666")
    assert gone is None


async def test_list_all(db):
    repo = UserRepository(db)
    await repo.create(name="Kim", email="kim@example.com", google_id="google-kim")
    await repo.create(name="Lee", email="lee@example.com", google_id="google-lee")
    users = await repo.list_all()
    emails = [u.email for u in users]
    assert "kim@example.com" in emails
    assert "lee@example.com" in emails


def auth_headers(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


async def test_get_me(client, db):
    repo = UserRepository(db)
    user = await repo.create(name="Tester", email="tester@example.com", google_id="g-tester")
    await db.commit()
    response = await client.get("/users/me", headers=auth_headers(user.id))
    assert response.status_code == 200
    assert response.json()["email"] == "tester@example.com"


async def test_add_phone_and_verify(client, db):
    repo = UserRepository(db)
    user = await repo.create(name="PhoneUser", email="phone@example.com", google_id="g-phone")
    await db.commit()

    with patch("app.routers.users.send_verification_sms") as mock_sms:
        mock_sms.return_value = None
        resp = await client.post(
            "/users/me/phones",
            json={"number": "+15551234567"},
            headers=auth_headers(user.id),
        )
    assert resp.status_code == 200

    phone = await repo.get_phone_by_number(user.id, "+15551234567")
    assert phone is not None
    code = phone.verification_code

    resp2 = await client.post(
        "/users/me/phones/verify",
        json={"number": "+15551234567", "code": code},
        headers=auth_headers(user.id),
    )
    assert resp2.status_code == 200
    assert resp2.json()["verified"] is True


async def test_get_my_wishlist(client, db):
    repo = UserRepository(db)
    user = await repo.create(name="Wish", email="wish@test.com", google_id="g-wish")
    phone = await repo.add_phone_number(user.id, "+15550001234")
    await repo.verify_phone(phone.id)
    await db.commit()

    owner = await OwnerRepository(db).resolve_or_create(name="Wish", phone_number="+15550001234")
    disc_repo = DiscRepository(db)
    await disc_repo.create(
        manufacturer="Innova", name="Teebird", color="Pink",
        input_date=date.today(), owner_id=owner.id, is_found=False
    )
    await db.commit()

    resp = await client.get("/users/me/wishlist", headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Teebird"


async def test_add_wishlist_disc(client, db):
    repo = UserRepository(db)
    user = await repo.create(name="WishAdd", email="wishadd@test.com", google_id="g-wishadd")
    phone = await repo.add_phone_number(user.id, "+15559990001")
    await repo.verify_phone(phone.id)
    await db.commit()

    resp = await client.post(
        "/users/me/wishlist",
        json={"manufacturer": "Discraft", "name": "Buzzz", "color": "White",
              "phone_number": "+15559990001"},
        headers=auth_headers(user.id),
    )
    assert resp.status_code == 201
    assert resp.json()["is_found"] is False
    assert resp.json()["owner"]["phone_number"] == "+15559990001"


async def test_wishlist_add_resolves_owner_no_heads_up(client, db):
    from sqlalchemy import select
    from app.models.pickup_event import SMSJob
    from app.models.owner import Owner

    # Create user and verify a phone
    repo = UserRepository(db)
    user = await repo.create(name="WishOwner", email="wishowner@test.com", google_id="g-wishowner")
    phone = await repo.add_phone_number(user.id, "+15551112222")
    await repo.verify_phone(phone.id)
    await db.commit()

    resp = await client.post(
        "/users/me/wishlist",
        headers=auth_headers(user.id),
        json={"phone_number": "+15551112222", "manufacturer": "Innova",
              "name": "Leopard", "color": "blue"},
    )
    assert resp.status_code == 201
    assert resp.json()["owner"]["phone_number"] == "+15551112222"

    # No SMS jobs for wishlist
    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert jobs == []

    # Owner row exists and is marked "not yet contacted"
    owner = (await db.execute(select(Owner))).scalar_one()
    assert owner.heads_up_sent_at is None
