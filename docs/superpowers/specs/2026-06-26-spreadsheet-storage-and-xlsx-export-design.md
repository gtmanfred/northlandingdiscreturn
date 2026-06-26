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

This work has two goals:
1. Make sure the app can store all information on the **Current** sheet.
2. Build an XLSX export feature that uses Roger's spreadsheet layout as its guide.

## Scope

**In scope** — driven by the Current sheet:
- Storage gaps that block Current-sheet data.
- Admin XLSX export matching the Current-sheet column layout, scoped by the active list filters.

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

## Frontend
- "Download spreadsheet" button on the disc-list view.
- Calls `GET /discs/export` with the currently active list filters (`is_found`, `is_returned`, `owner_name`).
- Triggers a browser file download of the returned `.xlsx`.

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

Frontend:
- Download button issues the request with active filters and saves the file.

## Trade-offs / decisions
- **Backend-generated XLSX** over client-side (SheetJS): openpyxl already present, filter and
  admin/user scoping logic stay in one place, date formatting handled server-side. Client-side
  would duplicate scoping and re-implement formatting in JS.
- **Date contacted derived** rather than a stored column: avoids a denormalized field that could
  fall out of sync with the notification records that already hold the source of truth.
- **`Code` / `Other` in `notes`** rather than a status enum or structured fields: per user direction,
  keeps the schema lean; the Current sheet's active rows carry little `Code`/`Other` structure.
