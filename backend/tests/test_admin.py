# backend/tests/test_admin.py
import pytest
from datetime import date, timedelta
from app.repositories.pickup_event import PickupEventRepository
from app.repositories.disc import DiscRepository


async def test_create_pickup_event(db):
    repo = PickupEventRepository(db)
    event = await repo.create_event(scheduled_date=date.today() + timedelta(days=7))
    assert event.id is not None
    assert event.notifications_sent_at is None


async def test_list_pickup_events(db):
    repo = PickupEventRepository(db)
    await repo.create_event(scheduled_date=date.today() + timedelta(days=7))
    await repo.create_event(scheduled_date=date.today() + timedelta(days=14))
    events = await repo.list_events()
    assert len(events) == 2


async def test_create_disc_notification(db):
    disc_repo = DiscRepository(db)
    event_repo = PickupEventRepository(db)
    disc = await disc_repo.create(
        manufacturer="Innova", name="Boss", color="Blue",
        input_date=date.today(), phone_number="+15551234567"
    )
    event = await event_repo.create_event(scheduled_date=date.today() + timedelta(days=3))
    notif = await event_repo.create_disc_notification(
        disc_id=disc.id, pickup_event_id=event.id, is_final_notice=False
    )
    assert notif.id is not None
    assert notif.is_final_notice is False


async def test_count_prior_notifications(db):
    disc_repo = DiscRepository(db)
    event_repo = PickupEventRepository(db)
    disc = await disc_repo.create(
        manufacturer="Innova", name="Wraith", color="Green",
        input_date=date.today(), phone_number="+15559999999"
    )
    for i in range(3):
        event = await event_repo.create_event(scheduled_date=date.today() + timedelta(days=i))
        await event_repo.create_disc_notification(disc_id=disc.id, pickup_event_id=event.id)
    count = await event_repo.count_notifications_for_disc(disc.id)
    assert count == 3


async def test_create_sms_job(db):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15550001111", message="Test message")
    assert job.id is not None
    assert job.status.value == "pending"


async def test_claim_pending_sms_jobs(db):
    repo = PickupEventRepository(db)
    await repo.create_sms_job(phone_number="+15550002222", message="Pickup notice")
    jobs = await repo.claim_pending_sms_jobs(limit=10)
    assert len(jobs) == 1
    assert all(j.status.value == "processing" for j in jobs)
