# backend/tests/test_users.py
import pytest
from app.repositories.user import UserRepository


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
