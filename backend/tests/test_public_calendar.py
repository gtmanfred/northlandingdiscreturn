from datetime import datetime, timedelta, timezone
from icalendar import Calendar

from app.repositories.pickup_event import PickupEventRepository


async def test_ics_feed_unauthenticated(client):
    resp = await client.get("/pickup-events.ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "max-age=300" in resp.headers.get("cache-control", "")
    Calendar.from_ical(resp.content)  # parses


async def test_ics_feed_only_includes_notified_events(client, db):
    repo = PickupEventRepository(db)
    start = datetime.now(timezone.utc) + timedelta(days=7)
    published = await repo.create_event(start_at=start, end_at=start + timedelta(hours=2))
    draft = await repo.create_event(start_at=start + timedelta(days=1), end_at=start + timedelta(days=1, hours=2))
    await repo.update_event(published, notifications_sent_at=datetime.now(timezone.utc))
    await db.commit()

    resp = await client.get("/pickup-events.ics")
    body = resp.content.decode()
    assert f"pickup-event-{published.id}@northlanding" in body
    assert f"pickup-event-{draft.id}@northlanding" not in body
