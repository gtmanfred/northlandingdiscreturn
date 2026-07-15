# Import Preview — Distinguish Discs That Will Text Owners

**Date:** 2026-07-15
**Status:** Approved
**Builds on:** 2026-07-15-import-preview-approve-design.md

## Problem

The import preview lists new discs but does not tell the admin which of them
will trigger an owner SMS on approval. Applying an import silently texts owners
of newly created, not-yet-returned discs. The admin should see, before
approving, exactly which new discs will send a text and which will not.

## Goal

In the preview's **New discs** bucket, split the discs into those that will text
the owner on apply and those that will not, with a reason for the latter.

## Non-Goals

- No change to who actually gets texted (apply behavior is unchanged).
- No opt-out lookup — enqueue happens regardless of opt-out (the worker skips
  opted-out numbers later), so an opt-out check would misrepresent what gets
  queued. Out of scope.
- Updated / unchanged discs and error rows are untouched — they never text.

## Behavior

On apply, a newly created disc enqueues owner SMS (heads-up, and welcome once per
owner) only when it is **not returned** and its owner has a **phone number**
(`backend/app/services/heads_up.py`, `welcome.py`). A returned disc never texts,
even with a phone.

The preview mirrors that with a row-only predicate (no extra DB reads):

- `will_notify = (not row.returned) and bool(row.phone)`
- `skip_reason`:
  - `"returned"` if `row.returned` (takes precedence),
  - else `"no phone"` if `row.phone` is falsy,
  - else `None`.

## Changes

### Backend — `plan_import` (`backend/app/services/disc_import.py`)

Each item in the plan's `created` list gains:
- `will_notify: bool`
- `skip_reason: str | None` (`"returned"` | `"no phone"` | `None`)

`ImportPlan.to_dict()["counts"]` gains `will_notify` — the number of created
discs with `will_notify == True`.

`updated`, `unchanged`, and `errors` are unchanged.

### Frontend — `ImportPreviewDialog` (`frontend/src/components/ImportPreviewDialog.tsx`)

Replace the single **New discs** expandable section with two expandable
sub-groups derived from `will_notify`:

- **New — will text owner (M)** — the `will_notify` discs.
- **New — no text (K)** — the rest; each row shows its `skip_reason`
  (`returned` / `no phone`).

Existing count tiles (new / updated / unchanged / errors) stay. The `PlannedNew`
type gains `will_notify: boolean` and `skip_reason: string | null`.

## Testing

Backend (`tests/test_disc_plan.py`):
- created disc, not returned, with phone → `will_notify == True`, `skip_reason
  is None`; `counts.will_notify == 1`.
- created disc, returned, with phone → `will_notify == False`, `skip_reason ==
  "returned"`.
- created disc, not returned, no phone → `will_notify == False`, `skip_reason ==
  "no phone"`.

Frontend (`ImportPreviewDialog.test.tsx`):
- a plan with both a will-text and a no-text new disc renders both sub-groups
  with their counts, and the no-text row shows its reason.

## Trade-offs

- Row-only predicate over an exact per-owner simulation: the welcome SMS also
  depends on `owner.welcome_sent_at`, but heads-up (the dominant, per-disc text)
  fires whenever not-returned + phone, so the predicate accurately reflects
  "this disc will text its owner." Keeping it row-only avoids per-row DB lookups
  in the read-only preview.
