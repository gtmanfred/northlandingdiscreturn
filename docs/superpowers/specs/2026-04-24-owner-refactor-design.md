# Owner / User Separation Refactor — Design

## Problem

Disc ownership is currently stored as freetext `owner_name` and `phone_number` columns on the `discs` table, with no canonical owner record. App users (Google-auth) are matched to their discs only by phone-number string comparison. This makes it impossible to:

- Track whether we have ever contacted a given owner, so we cannot send a "heads up" intro SMS the first time we find one of their discs.
- Deduplicate owners across discs in a structured way (for reporting, autocomplete, or future features).
- Cleanly separate the concepts of "owner of a disc" (contact target, not necessarily a user) and "app user" (Google-authenticated account).

Owners must be able to receive SMS notifications without ever becoming app users.

## Goals

1. Introduce a first-class `owners` table, keyed by `(name, phone_number)`.
2. Replace `discs.owner_name` and `discs.phone_number` with `discs.owner_id` (nullable FK).
3. Send a one-time heads-up SMS the first time we log a found disc for a new owner.
4. Preserve the existing "my discs" lookup for app users (matched via their verified phone numbers).
5. Provide autocomplete for owner name and phone number when admins log discs.

## Non-Goals

- Linking owners to users via explicit FK.
- Merging or splitting owner records after creation.
- Changing the SMS verification flow for app users.
- Changing pickup event scheduling or final-notice logic.

## Data Model

### New table: `owners`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID | PK |
| `name` | String | NOT NULL |
| `phone_number` | String | NOT NULL |
| `heads_up_sent_at` | DateTime(tz) | nullable |
| `created_at` | DateTime(tz) | server_default `now()` |
| `updated_at` | DateTime(tz) | server_default `now()`, onupdate `now()` |

Constraints and indexes:
- Unique constraint on `(name, phone_number)`.
- Index on `phone_number` (user → owner → discs lookup).
- Index on `name` (autocomplete).

`heads_up_sent_at` records only the heads-up intro SMS. Pickup notifications do not set this field.

### `discs` table changes

- Drop `owner_name` column.
- Drop `phone_number` column.
- Add `owner_id UUID` FK → `owners.id`, nullable, `ON DELETE SET NULL`.
- Index on `owner_id`.

Nullable `owner_id` preserves the ability to log a disc with no owner information.

## Data Migration

For each distinct `(owner_name, phone_number)` pair in `discs` where **both** fields are non-null:

1. Insert a row into `owners` with `name = owner_name`, `phone_number = phone_number`.
2. Set `heads_up_sent_at = MIN(discs.created_at)` across that owner's existing discs. (We assume pre-existing owners have already been contacted — do not retroactively send intro SMS.)
3. Update matching `discs.owner_id`.

Discs where either `owner_name` or `phone_number` is NULL get `owner_id = NULL`.

Only after the data move completes does the migration drop the two old columns.

## Heads-Up SMS Flow

Triggered on disc creation by the admin (not on user-submitted wishlist entries).

1. Resolve the owner: `SELECT ... WHERE name = ? AND phone_number = ?`. If no row, `INSERT` one.
2. Set `discs.owner_id` to that owner.
3. If `disc.is_found = True` AND `owner.heads_up_sent_at IS NULL`:
   - Enqueue an `SMSJob` with intro copy (see below).
   - Set `owner.heads_up_sent_at = now()`.

Intro copy (exact wording to be finalized at implementation):

> Hi {name}, this is North Landing Disc Return. We found one of your discs. We'll text you again when we schedule a pickup event — these happen every 1–2 months.

Wishlist entries (`is_found = False`, self-registered by a user) do NOT trigger a heads-up.

## User → Disc Lookup

`GET /me/discs` and `GET /me/wishlist`:

1. Load the user's verified phone numbers.
2. Find all `owners.id` where `owners.phone_number IN (verified_numbers)`.
3. Return discs where `discs.owner_id IN (those_owner_ids)` and `is_found`/`is_returned` filters match as today.

This matches on phone number alone — any owner name under a verified phone is considered the user's disc.

## Autocomplete

New endpoint: `GET /owners/suggest?q=<query>` (admin-only).

- Returns up to N owners (say, 10) where `name ILIKE q || '%'` OR `phone_number ILIKE q || '%'`.
- Response includes `id`, `name`, `phone_number`.
- Frontend disc-create form uses this for combined autocomplete: selecting a suggestion fills both fields; typing freely creates a new owner on submit (via the resolve-or-create path above).

## Notification Service

`enqueue_pickup_notifications` (backend/app/services/notification.py):

- Group unreturned found discs by `owner_id` (was: `phone_number`).
- Read the contact phone from `owners.phone_number`.
- Final-notice logic on `discs.final_notice_sent` is unchanged.
- Discs with `owner_id IS NULL` are skipped (as they are today when `phone_number IS NULL`).

## API Surface Changes

| Endpoint | Change |
|---|---|
| `POST /discs` (admin create) | Accepts `owner_name` + `phone_number` in the body as today; backend resolves/creates the owner row. |
| `PATCH /discs/{id}` | Same — mutating owner fields re-resolves the owner. Does not delete the old owner even if it becomes orphaned. |
| `GET /discs` | Response includes `owner: { id, name, phone_number, heads_up_sent_at }` (joined). `owner_name`/`phone_number` fields removed from disc payload. |
| `GET /me/discs`, `GET /me/wishlist` | Same shape, resolved via the phone → owner → disc path. |
| `GET /owners/suggest?q=` | New, admin-only. |

## Testing

- Unit: owner resolve-or-create (new + existing + name-variant cases).
- Unit: heads-up enqueued exactly once per owner; not enqueued for wishlist.
- Unit: notification service groups by owner_id.
- Integration: data-migration script produces the expected rows and sets `heads_up_sent_at` to the earliest disc date.
- Integration: `/me/discs` returns discs for any owner sharing a verified phone number, regardless of name.
- Integration: autocomplete returns matches by name prefix and by phone prefix.

## Open Risks

- **Phone number normalization.** Existing discs may have phone numbers stored in varying formats (`555-1234`, `5551234`, `+15551234`). The unique constraint on `(name, phone_number)` will treat these as distinct owners. Recommend normalizing to E.164 at write time and back-filling during migration. To be decided during implementation planning.
- **Heads-up timing.** If many discs are logged in rapid succession for a new owner, we still send exactly one heads-up because `heads_up_sent_at` is set in the same transaction as the SMSJob enqueue.
