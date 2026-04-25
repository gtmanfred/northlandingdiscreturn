# backend/tests/test_admin.py
import uuid
import pytest
from datetime import date, datetime, timedelta, timezone
from app.repositories.pickup_event import PickupEventRepository
from app.repositories.disc import DiscRepository
from app.repositories.owner import OwnerRepository
from app.services.auth import create_access_token
from app.repositories.user import UserRepository


def _window(days_from_now: int) -> dict:
    start = datetime.now(timezone.utc) + timedelta(days=days_from_now, hours=1)
    return {"start_at": start, "end_at": start + timedelta(hours=2)}


async def test_create_pickup_event(db):
    repo = PickupEventRepository(db)
    event = await repo.create_event(**_window(7))
    assert event.id is not None
    assert event.notifications_sent_at is None


async def test_list_pickup_events(db):
    repo = PickupEventRepository(db)
    await repo.create_event(**_window(7))
    await repo.create_event(**_window(14))
    events = await repo.list_events()
    assert len(events) == 2


async def test_create_disc_notification(db):
    disc_repo = DiscRepository(db)
    event_repo = PickupEventRepository(db)
    owner = await OwnerRepository(db).resolve_or_create(
        name="Boss Owner", phone_number="+15551234567"
    )
    disc = await disc_repo.create(
        manufacturer="Innova", name="Boss", color="Blue",
        input_date=date.today(), owner_id=owner.id,
    )
    event = await event_repo.create_event(**_window(3))
    notif = await event_repo.create_disc_notification(
        disc_id=disc.id, pickup_event_id=event.id, is_final_notice=False
    )
    assert notif.id is not None
    assert notif.is_final_notice is False


async def test_count_prior_notifications(db):
    disc_repo = DiscRepository(db)
    event_repo = PickupEventRepository(db)
    owner = await OwnerRepository(db).resolve_or_create(
        name="Wraith Owner", phone_number="+15559999999"
    )
    disc = await disc_repo.create(
        manufacturer="Innova", name="Wraith", color="Green",
        input_date=date.today(), owner_id=owner.id,
    )
    for i in range(3):
        event = await event_repo.create_event(**_window(i))
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


def admin_token(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


async def make_admin_user(db):
    repo = UserRepository(db)
    user = await repo.create(name="AdminUser", email="adm@test.com", google_id="g-adm")
    user.is_admin = True
    await db.commit()
    return user


async def test_list_users(client, db):
    admin = await make_admin_user(db)
    resp = await client.get("/admin/users", headers=admin_token(admin.id))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_create_pickup_event_endpoint(client, db):
    admin = await make_admin_user(db)
    start = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=7, hours=2)).isoformat()
    resp = await client.post(
        "/admin/pickup-events",
        json={"start_at": start, "end_at": end},
        headers=admin_token(admin.id),
    )
    assert resp.status_code == 201
    assert resp.json()["notifications_sent_at"] is None


async def test_notify_pickup_event(client, db):
    admin = await make_admin_user(db)
    disc_repo = DiscRepository(db)
    owner = await OwnerRepository(db).resolve_or_create(
        name="Notify Owner", phone_number="+15551112222"
    )
    await disc_repo.create(
        manufacturer="Innova", name="Wraith", color="Blue",
        input_date=date.today(), owner_id=owner.id, is_found=True,
    )
    await db.commit()

    start = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=3, hours=2)).isoformat()
    event_resp = await client.post(
        "/admin/pickup-events",
        json={"start_at": start, "end_at": end},
        headers=admin_token(admin.id),
    )
    event_id = event_resp.json()["id"]

    resp = await client.post(
        f"/admin/pickup-events/{event_id}/notify",
        headers=admin_token(admin.id),
    )
    assert resp.status_code == 200
    assert resp.json()["sms_jobs_enqueued"] == 1
    assert resp.json()["discs_notified"] == 1


async def test_cannot_demote_seed_admin(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "seed@test.com")
    from app.config import settings
    assert "seed@test.com" in settings.ADMIN_EMAILS
    admin = await make_admin_user(db)
    repo = UserRepository(db)
    seed = await repo.create(name="Seed", email="seed@test.com", google_id="g-seed")
    seed.is_admin = True
    await db.commit()

    resp = await client.patch(
        f"/admin/users/{seed.id}",
        json={"is_admin": False},
        headers=admin_token(admin.id),
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Cannot demote a seed admin"


async def test_can_demote_non_seed_admin(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "seed@test.com")
    from app.config import settings
    assert "seed@test.com" in settings.ADMIN_EMAILS
    admin = await make_admin_user(db)
    repo = UserRepository(db)
    other = await repo.create(name="Other", email="other@test.com", google_id="g-other")
    other.is_admin = True
    await db.commit()

    resp = await client.patch(
        f"/admin/users/{other.id}",
        json={"is_admin": False},
        headers=admin_token(admin.id),
    )
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False


async def test_update_event_bumps_sequence_on_time_change(db):
    repo = PickupEventRepository(db)
    event = await repo.create_event(**_window(7))
    assert event.sequence == 0
    new_start = event.start_at + timedelta(hours=1)
    new_end = event.end_at + timedelta(hours=1)
    await repo.update_event(event, start_at=new_start, end_at=new_end)
    assert event.sequence == 1


async def test_update_event_does_not_bump_when_unchanged(db):
    repo = PickupEventRepository(db)
    event = await repo.create_event(**_window(7), notes="hello")
    await repo.update_event(event, notes="hello")
    assert event.sequence == 0


async def test_edit_notified_event_bumps_sequence(client, db):
    admin = await make_admin_user(db)
    start = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=3, hours=2)).isoformat()
    create_resp = await client.post(
        "/admin/pickup-events",
        json={"start_at": start, "end_at": end},
        headers=admin_token(admin.id),
    )
    event_id = create_resp.json()["id"]
    assert create_resp.json()["sequence"] == 0

    # Force notifications_sent_at via a direct DB update (no discs to notify)
    from sqlalchemy import update
    from app.models.pickup_event import PickupEvent
    await db.execute(
        update(PickupEvent)
        .where(PickupEvent.id == uuid.UUID(event_id))
        .values(notifications_sent_at=datetime.now(timezone.utc))
    )
    await db.commit()

    new_start = (datetime.now(timezone.utc) + timedelta(days=3, hours=1)).isoformat()
    new_end = (datetime.now(timezone.utc) + timedelta(days=3, hours=3)).isoformat()
    patch_resp = await client.patch(
        f"/admin/pickup-events/{event_id}",
        json={"start_at": new_start, "end_at": new_end},
        headers=admin_token(admin.id),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["sequence"] == 1


async def test_create_event_rejects_reversed_window(client, db):
    admin = await make_admin_user(db)
    start = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=7) - timedelta(hours=1)).isoformat()
    resp = await client.post(
        "/admin/pickup-events",
        json={"start_at": start, "end_at": end},
        headers=admin_token(admin.id),
    )
    assert resp.status_code == 422
