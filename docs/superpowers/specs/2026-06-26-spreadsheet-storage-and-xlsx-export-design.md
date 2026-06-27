# Spreadsheet Storage Coverage + XLSX Export — Design

Date: 2026-06-26

## Background

Roger maintains a "North Landing Found Disc Spreadsheet" (`.xlsx`) outside the app.
It has five sheets; the four with data are:

| Sheet | Rows | Meaning |
|---|---|---|
| Current | ~290 | Active found discs, owner known, awaiting pickup |
| No Number | 1313 | Found discs, no contact phone |
| Returned | ~8400 | Archive — returned / donated / unclaimed / shipped |
| Hopefuls | 124 | People inquiring about a disc they lost |

Main-sheet columns: `Name, Phone, Mfr, Model, Color, Other, Code, Date found, Date returned, Date contacted`.
`Code` legend: `D=Donated, U=Unclaimed, S=Shipped, R=Returned`.

This work has three goals:
1. Make sure the app can store all information on the **Current** sheet.
2. Build an XLSX export feature that uses Roger's spreadsheet layout as its guide.
3. Import the Current sheet's data into the app, re-runnable as an upsert.

## Scope

**In scope** — driven by the Current sheet:
- Storage gaps that block Current-sheet data.
- Admin XLSX export matching the Current-sheet column layout, scoped by the active list filters.
- Admin XLSX import (upsert) of the Current sheet.

**Out of scope (future specs):**
- Hopefuls inquiry/claim model.
- No Number / Returned archive sheets and their `D/U/S` status codes.
- Structured decomposition of the free-text `Other` column (finder initials, `prev`/`no prev`, `house`). These stay in `notes`.

## Storage mapping (Current sheet → app model)

| Sheet column | App field | Action |
|---|---|---|
| Name | `Owner.first_name` / `Owner.last_name` | exists |
| Phone | `Owner.phone_number` | **make nullable** |
| Mfr | `Disc.manufacturer` | exists |
| Model | `Disc.name` | exists |
| Color | `Disc.colors[]` | exists |
| Other | `Disc.notes` | exists (free text; `Code` letter and finder notes live here) |
| Code | derived from status | `R` when returned, else blank |
| Date found | `Disc.input_date` | exists |
| Date returned | `Disc.returned_date` | **new column** |
| Date contacted | derived | **no column** — computed at export |

## Data model changes

### 1. `Owner.phone_number` nullable
- Change `phone_number` to `nullable=True`.
- Postgres composite uniques treat NULLs as distinct, so `uq_owners_first_last_phone` stays valid.
- Guard every SMS path so it skips (does not error) when an owner has no phone:
  heads-up, welcome, and pickup-notification senders.

### 2. `Disc.returned_date: Date | None`
- New nullable `Date` column.
- In `update_disc`, when `is_returned` transitions `false → true`, stamp `returned_date = today`.
  On `true → false`, clear it back to `None`.
- Existing returned discs backfill to `NULL` (return date unknown).

### 3. Date contacted — derived, not stored
- At export time: `latest of`
  - `owner.heads_up_sent_at`, and
  - `max(DiscPickupNotification.sent_at)` for that disc.
- Welcome texts are excluded (generic greeting, not disc-related).
- Result is a date (date portion of the latest timestamp), blank if none.

## Export feature

### Endpoint
- `GET /discs/export`, admin-only (`require_admin`, same as mutations).
- Query params identical to `GET /discs` list: `is_found`, `is_returned`, `owner_name`. No pagination — returns all matching rows.
- Response: `StreamingResponse` of an `.xlsx` built with openpyxl (already a dependency),
  `Content-Disposition: attachment; filename="north-landing-discs-<YYYY-MM-DD>.xlsx"`,
  content type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

### Filter reuse (no drift)
- Refactor the filter predicate construction currently inside `DiscRepository.list_all` /
  `count_all` into a shared private helper.
- Both the list endpoint and the export call the same helper so their result sets cannot diverge.

### Sheet layout (mirrors Current sheet)
- One worksheet.
- Title row, then column header row, then data rows.
- Columns in exact order: `Name, Phone, Mfr, Model, Color, Other, Code, Date found, Date returned, Date contacted`.
- `Date returned` and `Date contacted` columns are always present even though one is derived and one was just added — keeps the file a drop-in for Roger's format.

### Cell mapping
| Column | Value |
|---|---|
| Name | `owner.name`; blank or `?` when owner unknown |
| Phone | `owner.phone_number`; blank when null |
| Mfr | `disc.manufacturer` |
| Model | `disc.name` |
| Color | `disc.colors` joined by space |
| Other | `disc.notes` |
| Code | `R` if `is_returned`, else blank |
| Date found | `disc.input_date` (Excel date cell) |
| Date returned | `disc.returned_date` (Excel date cell), blank if none |
| Date contacted | derived date (Excel date cell), blank if none |

## Import feature

### Endpoint
- `POST /discs/import`, admin-only (`require_admin`).
- Accepts a multipart `.xlsx` upload (`UploadFile`).
- Parses the **Current** worksheet only (locate by sheet title `Current`; error if absent).
- Skips the title/subtitle/header rows; iterates data rows.
- Returns a JSON summary: `{ created, updated, skipped, errors: [{row, reason}] }`.

### Row parsing
| Sheet column | Parsed to |
|---|---|
| Name | split into `first_name` / `last_name`; single token → `last_name`, `first_name=""`; `?` or blank → both `""` |
| Phone | normalized phone string; blank → `None` |
| Mfr | `manufacturer` |
| Model | `name` |
| Color | normalized (trim, lowercase); stored in `colors[]` |
| Other | `notes` |
| Code / Date returned | drive returned status (see below) |
| Date found | `input_date` (required; row errors if unparseable) |

Owner resolution: if phone present (and/or a real name), `resolve_or_create` an owner with
`(first_name, last_name, phone_number)` and link it. If name and phone are both blank, leave
`owner_id` null.

### Upsert key
- A row is matched to an existing disc by:
  **`input_date` + `manufacturer` + `name` + normalized `colors` + owner `phone_number`.**
- All key components compared normalized (trim, case-insensitive); phone may be null.
- Accepted trade-off: editing an owner's phone in the app changes the key, so a re-upload of
  the unchanged sheet row will create a new disc rather than match the edited one.
- Collision note: two genuinely distinct discs with identical key fields (same disc, same day,
  same owner) collapse to one row. Acceptable; logged as an update, not an error.

### Upsert behavior
- **No match → create** a new disc (`is_found=true`).
- **Match → update** mutable fields whose value changed: `notes`, `colors`, owner link.
- **Returned status is one-way (sheet never un-returns):**
  - The sheet marks a disc returned when `Date returned` is populated or `Code` contains `R`.
  - If the sheet says returned and the app disc is not returned → set `is_returned=true` and
    `returned_date` (from the sheet's `Date returned`, or today if the code says returned with no date).
  - If the sheet does not say returned, leave the app disc's returned state untouched — an
    in-app return is never reverted by an import.

### Idempotency
- Re-uploading an unchanged sheet produces only `updated`/`skipped` with no data change
  (subject to the phone-edit caveat above).

## Frontend
- "Download spreadsheet" button on the disc-list view.
- Calls `GET /discs/export` with the currently active list filters (`is_found`, `is_returned`, `owner_name`).
- Triggers a browser file download of the returned `.xlsx`.
- "Import spreadsheet" control (admin-only) on the disc-list view: file picker → `POST /discs/import`.
- On success, show the summary (`created` / `updated` / `skipped` / errors) and refresh the list.

## Testing (TDD)

Backend:
- Filter helper: list and export produce the same disc set for the same params.
- Export endpoint:
  - returned `.xlsx` parses with openpyxl;
  - column set and order match the spec;
  - date cells are real Excel dates;
  - empty `Date returned` / `Date contacted` cells render blank, not `None`;
  - `Code` = `R` for returned, blank otherwise;
  - derived Date contacted = latest of heads-up and pickup-notification times;
  - non-admin caller → 403.
- `returned_date` stamped on `false→true`, cleared on `true→false`.
- Owner create/update with `phone_number = null` succeeds; SMS paths skip without error.

Import:
- New row → disc created with parsed fields and resolved owner.
- Re-upload unchanged → no changes (created=0), subject to phone-edit caveat.
- Changed `Other`/`Color`/owner → fields updated on the matched disc.
- Sheet marks returned → app disc set returned with `returned_date`.
- App disc returned, sheet active → stays returned (one-way).
- Row missing `Date found` → reported in `errors`, others still import.
- Name `?` / blank, phone blank → disc created with no owner.
- Missing `Current` sheet → request rejected.
- Non-admin caller → 403.

Frontend:
- Download button issues the request with active filters and saves the file.
- Import control uploads a file and renders the returned summary.

## Trade-offs / decisions
- **Backend-generated XLSX** over client-side (SheetJS): openpyxl already present, filter and
  admin/user scoping logic stay in one place, date formatting handled server-side. Client-side
  would duplicate scoping and re-implement formatting in JS.
- **Date contacted derived** rather than a stored column: avoids a denormalized field that could
  fall out of sync with the notification records that already hold the source of truth.
- **`Code` / `Other` in `notes`** rather than a status enum or structured fields: per user direction,
  keeps the schema lean; the Current sheet's active rows carry little `Code`/`Other` structure.
- **Import via admin upload endpoint** over a one-time CLI script: re-runnable from the UI as Roger's
  sheet evolves, and reuses the app's auth/owner-resolution paths.
- **Phone in the upsert key** (per user choice): stronger collision resistance, at the cost of
  re-creating a row when a phone is edited in-app. Documented above as an accepted trade-off.
- **One-way returns on import**: protects in-app returns from being reverted by a stale sheet.
