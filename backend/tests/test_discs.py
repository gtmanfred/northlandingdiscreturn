# backend/tests/test_discs.py
import pytest
from datetime import date
from app.repositories.disc import DiscRepository
from app.repositories.user import UserRepository


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
    assert len(discs) >= 2


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
