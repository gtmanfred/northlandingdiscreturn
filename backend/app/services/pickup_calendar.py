from __future__ import annotations
from typing import Iterable
from icalendar import Calendar, Event

from app.models.pickup_event import PickupEvent


def build_ics_feed(events: Iterable[PickupEvent]) -> str:
    cal = Calendar()
    cal.add("prodid", "-//North Landing Disc Return//pickup-events//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "North Landing Disc Pickups")

    for ev in events:
        vevent = Event()
        vevent.add("uid", f"pickup-event-{ev.id}@northlanding")
        vevent.add("dtstamp", ev.notifications_sent_at)
        vevent.add("dtstart", ev.start_at)
        vevent.add("dtend", ev.end_at)
        vevent.add("summary", "North Landing Disc Pickup")
        vevent.add("location", "North Landing Disc Golf Course")
        vevent.add("sequence", ev.sequence or 0)
        if ev.notes:
            vevent.add("description", ev.notes)
        cal.add_component(vevent)

    return cal.to_ical().decode("utf-8")
