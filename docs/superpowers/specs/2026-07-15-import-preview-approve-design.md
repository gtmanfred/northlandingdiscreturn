# Import Preview & Approve — Design

**Date:** 2026-07-15
**Status:** Approved

## Problem

The admin spreadsheet import is a one-shot action: selecting a file immediately
parses, merges into the database, commits, and enqueues SMS — with no chance to
review first. The admin only sees final counts, and error rows are hidden (a
count, never their contents). There is no safety gate before mutating data or
sending texts.

## Goals

- Before any write, show the admin what the spreadsheet *would* do: how many
  discs are new, updated, and unchanged.
- Let the admin browse which discs fall in the new and updated buckets, with
  old→new field diffs for updates.
- Display the full contents of every error row alongside its reason, for review.
- Require explicit approval before the merge (and before SMS is enqueued).

## Non-Goals

- No per-row accept/reject. Approval is all-or-nothing for the sheet.
- No editing of rows in the UI.
- No change to how discs are matched, created, or updated on apply (behavior of
  the existing merge is preserved exactly).

## Architecture

Split the import into two phases, both driven from stored parsed rows:

1. **Plan (read-only).** `plan_import(rows, db)` classifies each valid row
   against current DB state without writing anything — no owner creation, no
   disc writes, no SMS enqueue. Produces counts and per-bucket detail.
2. **Apply.** The current `import_rows` logic, renamed `apply_import(rows, db)`,
   is unchanged: it creates owners/discs, enqueues welcome + heads-up SMS, and
   the router commits. Apply re-runs its own lookups, so it self-corrects any DB
   drift between preview and approval; the stored plan is display-only.

`parse_current_sheet` is unchanged.

### `plan_import` classification

For each `ParsedDiscRow`:

- **Error** — `row.error` set or `input_date is None`. Capture the full parsed
  row content plus the reason.
- Otherwise resolve the owner **read-only** (look up by phone/name, never
  create) and find the existing disc via `find_by_import_key`.
  - No existing disc → **created**.
  - Existing disc → compute the same candidate updates the apply path computes
    (`notes`, `colors`, `owner` attach, one-way `is_returned`/`returned_date`).
    - Any updates → **updated**, with a list of `{field, old, new}` diffs.
    - No updates → **unchanged**.

Owner changes are represented semantically (old owner name/phone → new owner
name/phone from the row), not by `owner_id`, because a not-yet-created owner has
no id at plan time. `owner_id` equality is still what apply uses to decide the
write; the plan only needs to *show* the intended change.

The update-detection logic is shared between plan and apply (one helper that
returns the candidate `updates` dict given an existing disc + row) so the two
phases cannot drift.

## Data — new `import_staging` table

| column      | type        | notes                                             |
|-------------|-------------|---------------------------------------------------|
| id          | uuid PK     |                                                   |
| created_at  | timestamptz | server default now                                |
| created_by  | uuid FK users | admin who uploaded                              |
| filename    | text        | original upload name, for display                 |
| status      | text        | `pending` \| `applied` \| `canceled`              |
| rows        | JSONB       | serialized `ParsedDiscRow[]` — source of truth for apply |
| plan        | JSONB       | computed preview: counts + created / updated (with diffs) / unchanged / error lists |

Alembic migration adds the table. Model + repository follow existing patterns
(`app/models/`, `app/repositories/`).

**Lifecycle:** creating a new preview marks the uploader's prior `pending` rows
`canceled`, so at most one active preview exists per admin and stale rows do not
accumulate. No time-based expiry job in v1.

## API

Replaces `POST /discs/import` (only the admin UI calls it, so nothing else
breaks). All endpoints require admin.

- **`POST /discs/import/preview`** — multipart file.
  Parse → `plan_import` → cancel prior pending → insert staging row `pending`.
  Commits only the staging row (no disc/owner mutations). Returns
  `{staging_id, plan}`. Parse failure → 422 (as today).
- **`POST /discs/import/{staging_id}/apply`** — load staged rows →
  `apply_import` → commit → mark staging `applied`. Returns the real summary
  `{created, updated, skipped, errors}`. Not found → 404; status not `pending`
  → 409.
- **`POST /discs/import/{staging_id}/cancel`** — mark staging `canceled`
  (discard). Not found → 404; not `pending` → 409.

**Authorization trade-off (accepted):** all three endpoints require admin but do
NOT verify that `staging.created_by` equals the acting admin — any admin can
apply or cancel another admin's staged import if they have its id. The staging
id is server-side and only reachable via a direct API call (not the UI), and all
admins already share full disc/owner CRUD and can trigger the same owner SMS via
a normal import. Given that trusted-admin model, per-admin ownership scoping on
apply/cancel is intentionally omitted (the `create_pending` cancel-prior logic is
still scoped to the uploader, purely to bound stale rows).

## Frontend — AdminDiscsPage

Selecting a file calls `preview` (not the old direct import). On success, open a
**preview dialog**:

- Three count tiles: New, Updated, Unchanged.
- Expandable **New discs** list (mfr / model / colors / owner).
- Expandable **Updated discs** list, each showing old→new per changed field.
- **Error rows** table: full parsed cell contents + reason per row.
- Actions: **Approve & merge** → `apply` → toast the returned summary, refresh
  the disc list, close. **Cancel** → `cancel` endpoint, close.

Closing the dialog without approving calls `cancel` so no orphan `pending` row
lingers.

## Testing (TDD, red→green)

Backend:
- `plan_import`: created / updated / unchanged classification; diff computation
  for each mutable field; error-row capture with full content; **asserts no DB
  writes and no SMS enqueued** during plan.
- Shared update-detection helper: same result drives plan diffs and apply
  writes.
- Endpoints: preview stores a `pending` staging row and returns the plan;
  preview cancels the uploader's prior pending; apply commits, returns the
  summary, marks `applied`, and enqueues SMS; apply on non-pending → 409; apply
  unknown id → 404; cancel marks `canceled`.
- Migration applies against the existing test DB setup.

Frontend:
- Preview dialog renders count tiles, new/updated expandable lists (with diffs),
  and the error-rows table from a mocked plan.
- Approve calls apply and refreshes; Cancel (and dialog dismiss) calls cancel.

## Trade-offs

- **Server-side staging vs. re-uploading the file on approve.** Chose staging
  (a JSONB row) so approval works from the reviewed data and the file is parsed
  once. Cost: a new table + lifecycle. Accepted for a clean single source of
  truth.
- **Plan is display-only; apply re-runs lookups.** Avoids trusting possibly
  stale counts and keeps apply as the single authority on writes. Cost: minor
  duplicate lookup work; acceptable at this data scale.
- **One active preview per admin (cancel-prior)** instead of an expiry job —
  simplest thing that prevents stale accumulation (YAGNI).
