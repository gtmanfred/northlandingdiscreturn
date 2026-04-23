import uuid
from datetime import datetime, timezone
from icalendar import Calendar

from app.models.pickup_event import PickupEvent
from app.services.pickup_calendar import build_ics_feed


def _event(**overrides) -> PickupEvent:
    defaults = dict(
        id=uuid.uuid4(),
        start_at=datetime(2026, 5, 1, 20, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 5, 1, 22, 0, tzinfo=timezone.utc),
        notes=None,
        notifications_sent_at=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
        sequence=0,
    )
    defaults.update(overrides)
    ev = PickupEvent()
    for k, v in defaults.items():
        setattr(ev, k, v)
    return ev


def test_empty_feed_is_well_formed():
    feed = build_ics_feed([])
    cal = Calendar.from_ical(feed)
    assert cal.name == "VCALENDAR"
    assert list(cal.walk("VEVENT")) == []


def test_single_event_fields():
    ev = _event()
    feed = build_ics_feed([ev])
    cal = Calendar.from_ical(feed)
    vevents = list(cal.walk("VEVENT"))
    assert len(vevents) == 1
    ve = vevents[0]
    assert str(ve["UID"]) == f"pickup-event-{ev.id}@northlanding"
    assert ve["DTSTART"].dt == ev.start_at
    assert ve["DTEND"].dt == ev.end_at
    assert str(ve["SUMMARY"]) == "North Landing Disc Pickup"
    assert str(ve["LOCATION"]) == "North Landing Disc Golf Course"
    assert int(ve["SEQUENCE"]) == 0
    assert "DESCRIPTION" not in ve


def test_event_with_notes_has_description():
    ev = _event(notes="Bring ID; gate code 1234")
    feed = build_ics_feed([ev])
    cal = Calendar.from_ical(feed)
    ve = list(cal.walk("VEVENT"))[0]
    assert "Bring ID; gate code 1234" in str(ve["DESCRIPTION"])


def test_sequence_reflected():
    ev = _event(sequence=3)
    feed = build_ics_feed([ev])
    cal = Calendar.from_ical(feed)
    ve = list(cal.walk("VEVENT"))[0]
    assert int(ve["SEQUENCE"]) == 3


def test_notes_with_special_chars_roundtrip():
    ev = _event(notes="Line 1\nLine 2, with comma; and semicolon")
    feed = build_ics_feed([ev])
    cal = Calendar.from_ical(feed)
    ve = list(cal.walk("VEVENT"))[0]
    desc = str(ve["DESCRIPTION"])
    assert "Line 1" in desc and "Line 2" in desc
    assert "comma" in desc and "semicolon" in desc
