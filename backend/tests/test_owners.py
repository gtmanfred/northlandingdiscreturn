import uuid
from app.models.owner import Owner


async def test_owner_model_persists(db):
    owner = Owner(name="John Smith", phone_number="+15551234567")
    db.add(owner)
    await db.flush()
    await db.refresh(owner)
    assert isinstance(owner.id, uuid.UUID)
    assert owner.name == "John Smith"
    assert owner.phone_number == "+15551234567"
    assert owner.heads_up_sent_at is None
    assert owner.created_at is not None


async def test_owner_unique_name_phone(db):
    from sqlalchemy.exc import IntegrityError
    db.add(Owner(name="Jane", phone_number="+15550001111"))
    await db.flush()
    db.add(Owner(name="Jane", phone_number="+15550001111"))
    try:
        await db.flush()
        assert False, "should have raised IntegrityError"
    except IntegrityError:
        await db.rollback()
