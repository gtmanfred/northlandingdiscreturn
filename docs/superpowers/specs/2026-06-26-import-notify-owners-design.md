# Import Notifies Owners of Newly-Created Discs — Design

Date: 2026-06-26

## Background

`POST /discs/import` (the Current-sheet upsert) currently creates discs silently — it
calls `DiscRepository.create` directly and never enqueues the welcome / heads-up SMS that
the single-disc add path (`POST /discs`) sends. Owners of discs added via import are never
notified.

This change makes import notify owners of discs it **creates**, matching the single-disc
add behavior.

## Decision

- **Always notify** on created discs — no toggle, no new endpoint parameter.
- The first import into an empty database will therefore enqueue a welcome + heads-up for
  every new owner/disc (~290 on the initial load). This is accepted: import is an upsert, so
  subsequent imports only notify genuinely new rows (existing rows match and stay silent).

## Behavior

In `import_rows`, for each row that results in a **create** (not update, not skip):

1. Enqueue welcome, then heads-up, in that order (same order as `POST /discs`):
   - `maybe_enqueue_welcome(owner=owner, db=db)`
   - `maybe_enqueue_heads_up(owner=owner, disc=disc, db=db)`

Reuse the existing service functions — do not duplicate SMS logic.

### Skips (no texts)

- **No phone:** `maybe_enqueue_welcome` and `maybe_enqueue_heads_up` already return early when
  `owner.phone_number` is falsy. No extra guard needed, but the import must still have an owner
  object to call them.
- **No owner:** rows with neither name nor phone resolve to `owner_id=None`; skip both calls.
- **Created-as-returned rows:** when a created row is marked returned from the sheet, do **not**
  notify — a disc that is already returned should not trigger a "we found your disc" text.
- **Updated / matched / skipped rows:** never notify.

### Dedup

- Welcome dedup is owner-level via `owner.welcome_sent_at` (the service guard). Two created
  discs for the same owner in one import → welcome enqueued once, heads-up twice.

## Plumbing

`import_rows` already resolves the owner with `OwnerRepository.resolve_or_create`, which returns
the `Owner` instance. Capture that instance (currently only `owner.id` is kept) so it can be
passed to the senders. The disc passed to `maybe_enqueue_heads_up` is the freshly-created `Disc`
(its `manufacturer`, `name`, `colors`, and `is_found=True` are all set; the sender reads the
owner from the explicit argument, not `disc.owner`).

The endpoint continues to `await db.commit()` once after `import_rows` returns; the enqueued
`SMSJob` rows are persisted by that commit, the same as the create endpoint.

## Testing (TDD)

- Created disc with phone + name → one welcome and one heads-up `SMSJob` enqueued.
- Two created discs, same owner → welcome enqueued once, heads-up enqueued twice.
- Row that matches an existing disc (update or skip) → no new `SMSJob`.
- Created row marked returned from the sheet → no `SMSJob`.
- Created disc whose owner has a null phone → no `SMSJob`.

## Out of scope

- Any notify toggle, checkbox, or endpoint parameter.
- Notifying on updated rows.
- Changing the welcome/heads-up message content or the single-disc add path.
