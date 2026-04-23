# Pickup Event Time Windows + ICS Calendar Feed

**Date:** 2026-04-23
**Status:** Approved for implementation

## Summary

Pickup events currently carry a calendar date only. Admins and disc owners
need to know *when during that day* pickup is happening, and owners want to
subscribe to pickup dates in their calendar apps instead of relying on SMS
reminders alone.

Two changes:

1. Replace the single `scheduled_date` field with a start/end timestamp
   window (stored UTC, displayed in the course's local timezone).
2. Publish a public, unauthenticated iCalendar (`.ics`) feed containing every
   pickup event that has had notifications sent — turning "Send
   Notifications" into the publish trigger for the calendar feed too.

## Non-goals

- No event deletion or cancellation workflow (existing behavior preserved).
  If later needed, cancellation would emit `STATUS:CANCELLED` on the VEVENT
  rather than removing the row.
- No per-user authenticated feed. One public feed for all events.
- No public-facing pickup events page beyond the subscribe link on the
  login page.

## Data model

### New columns on `pickup_events`

| Column | Type | Notes |
|---|---|---|
| `start_at` | `DateTime(timezone=True)`, not null | Event start, UTC |
| `end_at` | `DateTime(timezone=True)`, not null | Event end, UTC. Must be > `start_at` |
| `sequence` | `Integer`, not null, default 0 | Incremented on every update. Emitted as `SEQUENCE` in the ics file so subscribed clients see edits |

### Removed

- `scheduled_date` (`Date`) — dropped after migration.

### Alembic migration

One migration file:

1. Add `start_at`, `end_at` as nullable, `sequence` with default 0.
2. Backfill existing rows: `start_at = scheduled_date @ 16:00 America/New_York`,
   `end_at = scheduled_date @ 18:00 America/New_York`, both converted to UTC.
3. Alter `start_at` and `end_at` to not null.
4. Drop `scheduled_date`.

Downgrade restores `scheduled_date` from `start_at::date` in course local
time, and drops the new columns.

### Timezone constant

New module `backend/app/core/timezone.py`:

```python
COURSE_TIMEZONE = "America/New_York"
```

Used by the migration, the ics generator, and anywhere else the server
needs to reason about course-local time. Frontend imports the same IANA
string via a small constant (hardcoded in the frontend — no runtime API
call needed for something this stable).

## API changes

### Schemas

`backend/app/schemas/pickup_event.py`:

- `PickupEventCreate`: `start_at: datetime`, `end_at: datetime`,
  `notes: str | None`. Validator: `end_at > start_at`. Reject `start_at`
  more than 365 days in the future (basic sanity).
- `PickupEventUpdate`: all three fields optional; same cross-field
  validation when both times are present (or one is present and the other
  is known on the existing row — validate at the service layer after
  merging).
- `PickupEventOut`: exposes `id`, `start_at`, `end_at`, `notes`,
  `notifications_sent_at`, `sequence`, `created_at`.

### Existing admin endpoints

Unchanged paths and operation IDs. Behavior changes:

- `POST /admin/pickup-events` — takes the new fields.
- `PATCH /admin/pickup-events/{id}` — takes the new fields. Increments
  `sequence` whenever any of `start_at`, `end_at`, or `notes` actually
  changed. Allowed even after `notifications_sent_at` is set (this is how
  published events get corrected).
- `POST /admin/pickup-events/{id}/notify` — unchanged apart from the fact
  that it is now the publish trigger for the ics feed.

### New public endpoint

`GET /pickup-events.ics` — mounted at the application root (not under
`/admin`), unauthenticated.

- Response content type: `text/calendar; charset=utf-8`
- Header: `Content-Disposition: inline; filename="pickup-events.ics"`
- Header: `Cache-Control: public, max-age=300`
- Body: a VCALENDAR containing one VEVENT per pickup event where
  `notifications_sent_at IS NOT NULL`. No filter on date — past and future
  events both included.

### VEVENT format

Per event:

| Field | Value |
|---|---|
| `UID` | `pickup-event-<event.id>@northlanding` (stable per event row) |
| `DTSTAMP` | `notifications_sent_at` in UTC |
| `DTSTART` | `start_at` in UTC (`...Z` form) |
| `DTEND` | `end_at` in UTC |
| `SUMMARY` | `North Landing Disc Pickup` |
| `DESCRIPTION` | `event.notes` if set, otherwise omitted |
| `LOCATION` | `North Landing Disc Golf Course` |
| `SEQUENCE` | `event.sequence` |

Generation uses the [`ics`](https://pypi.org/project/ics/) Python package
(add to `pyproject.toml`). No hand-rolled VCALENDAR string escaping.

### Backend file layout

- `backend/app/core/timezone.py` — `COURSE_TIMEZONE` constant.
- `backend/app/services/pickup_calendar.py` — pure function
  `build_ics_feed(events) -> str` that takes a list of pickup events and
  returns the VCALENDAR text. Unit-testable without FastAPI.
- New router `backend/app/routers/public_calendar.py` (or add to an
  existing public router if one exists) — exposes `GET
  /pickup-events.ics`. Mounted in `main.py`.

## Frontend changes

### Generated types

Running Orval regenerates types once the OpenAPI schema updates. No
hand-maintained type changes needed, apart from replacing usages of the
old `scheduled_date` field.

### `AdminPickupEventsPage.tsx`

**Create form**: three inputs.

- `<input type="date">` — required, no default.
- `<input type="time">` — required, default `16:00`.
- `<input type="time">` — required, default `18:00`.
- `<input type="text">` for notes — unchanged.

Client-side: combine date + time in course-local timezone using
`date-fns-tz` (add as a dependency if not already present). Convert to ISO
UTC before posting. Validate `end > start` before submit.

**Event list row**: show a formatted window like `Apr 30, 2026 ·
4:00–6:00 PM ET` using `date-fns-tz` with `COURSE_TIMEZONE`.

**Inline edit**: new "Edit" button per row. Opens the same three-input
form prefilled from the event (times rendered in course-local). Submits
via PATCH. After notifications have been sent, editing is still allowed —
backend bumps `sequence`.

**Subscribe box**: a small read-only block at the top of the page showing
the full feed URL (`<origin>/pickup-events.ics`) with a Copy button and
a one-line explainer ("Subscribe in Google/Apple/Outlook Calendar to see
published pickup events"). The origin comes from `window.location.origin`
— no new config needed.

### `LoginPage.tsx`

Add a small "📅 Subscribe to pickup calendar" link beneath the login
controls. Clicking copies the `/pickup-events.ics` URL to clipboard (and
falls back to navigating to it if clipboard is unavailable). This is the
only public-facing discovery surface.

### `index.html`

Add `<link rel="alternate" type="text/calendar" title="North Landing Disc
Pickup Events" href="/pickup-events.ics">` so browser extensions and apps
that sniff for calendar feeds can auto-detect.

## Error handling

- Migration: if any existing pickup event has a null `scheduled_date`
  (shouldn't happen given existing schema), migration fails loudly rather
  than inventing data.
- API: invalid windows (`end_at <= start_at`, `start_at` too far future)
  return 422 with a clear field error.
- ics endpoint: returns an empty but well-formed VCALENDAR (just
  `BEGIN:VCALENDAR...END:VCALENDAR`) if no events have been notified.
  Never 404.

## Testing

### Backend

- `test_pickup_calendar.py`: unit tests for `build_ics_feed`.
  - Empty event list → well-formed empty VCALENDAR.
  - One event → correct `DTSTART`/`DTEND` in UTC, stable UID, SEQUENCE
    reflected.
  - Event with notes → `DESCRIPTION` present; without notes → absent.
  - Escaping: notes containing commas, semicolons, newlines survive a
    round-trip parse by the `ics` library.
- Router test for `GET /pickup-events.ics`:
  - Unauthenticated access works.
  - Only events with `notifications_sent_at IS NOT NULL` are included.
  - Cache-Control and Content-Type headers set.
- Router tests for create/update:
  - `end_at <= start_at` → 422.
  - Update to a notified event bumps `sequence`.
  - Update with no actual changes does not bump `sequence`.
- Migration test: an integration test that inserts a `scheduled_date`-only
  row via raw SQL in the pre-migration schema, runs the upgrade, and
  confirms the 4pm–6pm ET backfill.

### Frontend

- Component test for the create form: picking date 2026-05-01 + default
  times posts ISO UTC that corresponds to 2026-05-01T16:00 and 18:00
  America/New_York.
- Formatting test for the list row (course-local rendering).
- `LoginPage` subscribe link copies the expected URL.

## Open questions

None — all resolved during brainstorming.
