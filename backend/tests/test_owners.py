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


from datetime import date
from app.models.disc import Disc


async def test_disc_has_owner_relationship(db):
    owner = Owner(name="Ada", phone_number="+15559990000")
    db.add(owner)
    await db.flush()
    disc = Disc(
        manufacturer="Innova",
        name="Destroyer",
        color="red",
        input_date=date(2026, 4, 1),
        owner_id=owner.id,
    )
    db.add(disc)
    await db.flush()
    await db.refresh(disc)
    assert disc.owner_id == owner.id
    assert disc.owner.name == "Ada"


async def test_disc_owner_id_nullable(db):
    disc = Disc(
        manufacturer="Innova",
        name="Wraith",
        color="blue",
        input_date=date(2026, 4, 1),
    )
    db.add(disc)
    await db.flush()
    await db.refresh(disc)
    assert disc.owner_id is None


from app.repositories.owner import OwnerRepository


async def test_repo_resolve_creates_new_owner(db):
    repo = OwnerRepository(db)
    owner = await repo.resolve_or_create(name="Jill", phone_number="+15551111111")
    assert owner.id is not None
    assert owner.heads_up_sent_at is None
    await db.commit()


async def test_repo_resolve_returns_existing_owner(db):
    repo = OwnerRepository(db)
    first = await repo.resolve_or_create(name="Jack", phone_number="+15552222222")
    await db.commit()
    second = await repo.resolve_or_create(name="Jack", phone_number="+15552222222")
    assert first.id == second.id


async def test_repo_get_by_phones(db):
    repo = OwnerRepository(db)
    a = await repo.resolve_or_create(name="A", phone_number="+15553333333")
    b = await repo.resolve_or_create(name="B", phone_number="+15553333333")
    await repo.resolve_or_create(name="C", phone_number="+15559999999")
    await db.commit()
    owners = await repo.list_by_phones(["+15553333333"])
    assert {o.id for o in owners} == {a.id, b.id}


async def test_repo_mark_heads_up_sent(db):
    repo = OwnerRepository(db)
    owner = await repo.resolve_or_create(name="D", phone_number="+15554444444")
    await db.commit()
    assert owner.heads_up_sent_at is None
    await repo.mark_heads_up_sent(owner)
    await db.commit()
    await db.refresh(owner)
    assert owner.heads_up_sent_at is not None


from app.schemas.disc import DiscOut


async def test_disc_out_embeds_owner(db):
    from app.repositories.owner import OwnerRepository
    from app.repositories.disc import DiscRepository
    from datetime import date
    disc_repo = DiscRepository(db)
    owner = await OwnerRepository(db).resolve_or_create(
        name="Eva", phone_number="+15555555555"
    )
    disc = await disc_repo.create(
        manufacturer="MVP", name="Wave", color="green",
        input_date=date(2026, 4, 1), owner_id=owner.id,
    )
    await db.commit()
    disc = await disc_repo.get_by_id(disc.id)
    out = DiscOut.model_validate(disc)
    assert out.owner is not None
    assert out.owner.name == "Eva"
    assert out.owner.phone_number == "+15555555555"


async def test_disc_repo_create_with_owner_id(db):
    from app.repositories.owner import OwnerRepository
    from app.repositories.disc import DiscRepository
    from datetime import date
    owner = await OwnerRepository(db).resolve_or_create(
        name="Fred", phone_number="+15556666666"
    )
    disc = await DiscRepository(db).create(
        manufacturer="Discraft", name="Buzzz", color="yellow",
        input_date=date(2026, 4, 1), owner_id=owner.id,
    )
    await db.commit()
    assert disc.owner_id == owner.id


async def test_disc_repo_list_by_owner_ids(db):
    from app.repositories.owner import OwnerRepository
    from app.repositories.disc import DiscRepository
    from datetime import date
    repo = DiscRepository(db)
    o1 = await OwnerRepository(db).resolve_or_create(name="G", phone_number="+15557000001")
    o2 = await OwnerRepository(db).resolve_or_create(name="H", phone_number="+15557000002")
    d1 = await repo.create(manufacturer="m", name="n", color="c",
                           input_date=date(2026,4,1), owner_id=o1.id)
    d2 = await repo.create(manufacturer="m", name="n", color="c",
                           input_date=date(2026,4,1), owner_id=o2.id, is_found=False)
    await db.commit()
    found = await repo.list_found_by_owner_ids([o1.id, o2.id])
    wish = await repo.list_wishlist_by_owner_ids([o1.id, o2.id])
    assert {d.id for d in found} == {d1.id}
    assert {d.id for d in wish} == {d2.id}


from sqlalchemy import select
from app.models.pickup_event import SMSJob


async def test_heads_up_enqueued_on_first_found_disc(db):
    from app.services.heads_up import maybe_enqueue_heads_up
    from app.repositories.owner import OwnerRepository

    owner = await OwnerRepository(db).resolve_or_create(
        name="Iris", phone_number="+15558000001"
    )
    await db.commit()

    sent = await maybe_enqueue_heads_up(owner=owner, is_found=True, db=db)
    await db.commit()
    assert sent is True
    await db.refresh(owner)
    assert owner.heads_up_sent_at is not None

    jobs = (await db.execute(select(SMSJob).where(SMSJob.phone_number == owner.phone_number))).scalars().all()
    assert len(jobs) == 1
    assert "North Landing Disc Return" in jobs[0].message


async def test_heads_up_not_re_enqueued(db):
    from app.services.heads_up import maybe_enqueue_heads_up
    from app.repositories.owner import OwnerRepository
    owner = await OwnerRepository(db).resolve_or_create(
        name="Jay", phone_number="+15558000002"
    )
    await db.commit()
    await maybe_enqueue_heads_up(owner=owner, is_found=True, db=db)
    await db.commit()
    sent_again = await maybe_enqueue_heads_up(owner=owner, is_found=True, db=db)
    await db.commit()
    assert sent_again is False
    jobs = (await db.execute(select(SMSJob).where(SMSJob.phone_number == owner.phone_number))).scalars().all()
    assert len(jobs) == 1


async def test_heads_up_not_enqueued_for_wishlist(db):
    from app.services.heads_up import maybe_enqueue_heads_up
    from app.repositories.owner import OwnerRepository
    owner = await OwnerRepository(db).resolve_or_create(
        name="Kay", phone_number="+15558000003"
    )
    await db.commit()
    sent = await maybe_enqueue_heads_up(owner=owner, is_found=False, db=db)
    await db.commit()
    assert sent is False
    await db.refresh(owner)
    assert owner.heads_up_sent_at is None


async def test_notification_groups_by_owner(db):
    from datetime import date, datetime, timezone
    from app.repositories.owner import OwnerRepository
    from app.repositories.disc import DiscRepository
    from app.repositories.pickup_event import PickupEventRepository
    from app.services.notification import enqueue_pickup_notifications
    from app.models.pickup_event import SMSJob
    from sqlalchemy import select

    o1 = await OwnerRepository(db).resolve_or_create(
        name="Leo", phone_number="+15559000001"
    )
    o2 = await OwnerRepository(db).resolve_or_create(
        name="Mia", phone_number="+15559000002"
    )
    disc_repo = DiscRepository(db)
    await disc_repo.create(manufacturer="i", name="n", color="r",
                           input_date=date(2026,4,1), owner_id=o1.id)
    await disc_repo.create(manufacturer="i", name="n", color="g",
                           input_date=date(2026,4,1), owner_id=o1.id)
    await disc_repo.create(manufacturer="d", name="b", color="y",
                           input_date=date(2026,4,1), owner_id=o2.id)
    event = await PickupEventRepository(db).create_event(
        start_at=datetime(2026, 5, 1, 20, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 5, 1, 22, 0, tzinfo=timezone.utc),
        notes=None,
    )
    await db.commit()

    sms_count, disc_count = await enqueue_pickup_notifications(event, db)
    await db.commit()
    assert disc_count == 3
    assert sms_count == 2  # one per owner

    jobs = (await db.execute(select(SMSJob))).scalars().all()
    # Exclude any heads-up jobs (there shouldn't be any here since owners were
    # created via the repo, not the admin create flow).
    phones = sorted(j.phone_number for j in jobs)
    assert phones == ["+15559000001", "+15559000002"]
