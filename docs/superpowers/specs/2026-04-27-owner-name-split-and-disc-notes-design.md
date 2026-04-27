# Owner First/Last Name Split + Disc Notes — Design

## Problem

The `owners` table stores a single `name` string. We want structured
first/last names for owners so admins can search/sort cleanly and so the
import script can interpret a comma-separated name from the source
spreadsheet (where the convention is `"First, Last"` — first name in
front of the comma).

Separately, admins want a free-text `notes` field on each disc to record
identifying details ("blue marker on rim", "found near hole 7", etc.).
Wishlist users (who self-register lost discs) should also be able to
attach a note describing the disc, visible to admins.

## Goals

1. Replace `owners.name` with `owners.first_name` + `owners.last_name`.
2. Backfill existing owner rows by splitting `name` on the first space.
3. Import script parses spreadsheet name field via the comma rule
   (`"First, Last"` → first=before, last=after); falls back to the
   first-space rule otherwise.
4. Admin disc form collects first/last name in separate inputs, each
   with its own autocomplete.
5. Add a `notes` field to discs. Admin-only on found discs; user-writable
   and user-visible on the user's own wishlist entries.

## Non-Goals

- Merging or deduping existing owner records.
- Renaming the heads-up SMS, autocomplete endpoints, or pickup logic.
- Adding a notes column to the spreadsheet or import script.
- Showing admin-written notes to disc owners.

## Data Model

### `owners` table

- Drop `name`.
- Add `first_name VARCHAR NOT NULL`.
- Add `last_name VARCHAR NOT NULL DEFAULT ''` (empty string for
  single-token names like "Cher").
- Replace the existing `(name, phone_number)` unique constraint with
  `uq_owners_first_last_phone` on `(first_name, last_name, phone_number)`.
- Drop the existing `ix_owners_name` index. Add a composite index on
  `(last_name, first_name)` to support autocomplete and sorted listing.

### `discs` table

- Add `notes TEXT NULL`. Null = no note.

## Migration

For each row in `owners`:

- Split `name` on the **first space**.
  - `"John Smith"` → `first_name="John"`, `last_name="Smith"`.
  - `"Mary Jane Watson"` → `first_name="Mary"`, `last_name="Jane Watson"`.
  - `"Cher"` → `first_name="Cher"`, `last_name=""`.
- Drop `name`.

Then drop `ix_owners_name` and `uq_owners_name_phone`, create the new
composite index, dedup any rows that collapse to the same
`(first_name, last_name, phone_number)` triple (keep the oldest, repoint
its `discs.owner_id` references, delete the rest), and add the
`uq_owners_first_last_phone` unique constraint. The migration is one
Alembic revision; columns and constraints change in the same revision.

## Owner Name Parsing Helper

Backend module: `backend/app/owner_name.py` (new).

```python
def parse_owner_name(raw: str) -> tuple[str, str]:
    """Parse a freeform name into (first_name, last_name).

    - If the input contains a comma, split on the first comma:
      'Doe, John' -> ('Doe', 'John')  (first name in front of comma)
    - Else, split on the first space:
      'John Smith' -> ('John', 'Smith')
      'Cher'       -> ('Cher', '')
    - Empty / whitespace-only input -> ('', '').
    - Both halves are stripped.
    """
```

Used by:

- The admin disc create/update endpoints when the client passes a
  single combined name (see *API Surface* — kept for backward-compat).
- The import script (duplicated in Python with identical semantics —
  the script does not import backend modules; it uses the HTTP API).

## Owner Resolution

`OwnerRepository.resolve_or_create(first_name, last_name, phone_number)`:

- Lookup: `WHERE first_name = ? AND last_name = ? AND phone_number = ?`.
- If found, return it.
- Else insert a new row.

The `uq_owners_first_last_phone` unique constraint enforces that there
is at most one row per triple, so the lookup-then-insert pattern is
race-safe — a concurrent insert that beats us to it raises
`IntegrityError`, and the next request resolves to the existing row.

## Heads-Up SMS

Unchanged behavior. Resolved owner is keyed by the new triple; the
`heads_up_sent_at` flag still gates the one-time intro SMS.

## API Surface Changes

### `OwnerOut`

```python
class OwnerOut(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    name: str          # computed: f"{first_name} {last_name}".strip()
    phone_number: str
    heads_up_sent_at: datetime | None
    created_at: datetime
```

The computed `name` is read-only and exists so existing display code
("show owner") doesn't have to change in lockstep.

### `DiscCreate` / `DiscUpdate`

Replace `owner_name: str | None` with:

- `owner_first_name: str | None`
- `owner_last_name: str | None`

Validator: `owner_first_name`, `owner_last_name`, and `phone_number`
must all be provided together or all omitted. (`owner_last_name=""` is
valid when paired with the other two — empty string is a real value for
single-token names.)

### `DiscOut`

Add `notes: str | None`.

- Admin endpoints (`GET /discs`, `GET /discs/{id}`): return as stored.
- `GET /me/discs` (user's *found* discs): always return `None` for
  `notes`. Strip at the response-shaping layer in the router.
- `GET /me/wishlist`: return as stored (user wrote it themselves).

### `WishlistDiscCreate`

Add `notes: str | None = None`.

### Suggestions endpoint

`GET /suggestions?field=owner_name` is replaced by two fields:

- `field=owner_first_name`
- `field=owner_last_name`

Each returns distinct values from `owners`, ordered case-insensitively.

`/owners/suggest?q=...` (introduced in the prior owner-refactor) is
updated to match `q` against either name part or phone number, and to
return `{ id, first_name, last_name, phone_number }`.

## Frontend

### Admin disc form (`AdminDiscFormPage`)

- Replace the single "Owner name" `AutocompleteInput` with two
  side-by-side inputs:
  - **First name** — autocomplete from `owner_first_name` suggestions.
  - **Last name** — autocomplete from `owner_last_name` suggestions.
- Phone autocomplete (`useGetPhoneSuggestions`) takes both names and
  returns numbers for any owner where both prefixes match (treat empty
  string as "no constraint").
- Form state: replace `owner_name` with `owner_first_name` and
  `owner_last_name`. Editing either name resets `phone_number` (same
  behavior as today).
- Add a **Notes** `<textarea>` (optional, full-width, beneath the flag
  checkboxes). Submitted as `notes` on create/update.

### Admin disc list / detail

- Owner column: `f"{first} {last}".strip()`.
- Notes: show under the disc card title in admin views (when present).
- Owner filter: server-side `ILIKE` over the concatenation
  `first_name || ' ' || last_name`. The query field stays as one
  combined input on the admin filter bar.

### `MyWishlistPage`

- Add a **Notes** single-line text input (optional) to the add-disc
  form, alongside manufacturer/name/color.
- Display each wishlist row's notes (when present) as a muted line
  under the disc info.
- The user's name comes from `useGetMe()` and is parsed once via
  `parse_owner_name` (frontend port — see below) before sending to
  `POST /me/wishlist`.

### `MyDiscsPage`

No change — notes are not shown for found discs.

### Frontend name parser

`frontend/src/utils/ownerName.ts`:

```ts
export function parseOwnerName(raw: string): {
  first_name: string
  last_name: string
}
```

Same rules as the backend helper (comma first, then first space).

## Import Script (`scripts/import_discs.py`)

- Replace `ParsedRow.name: str | None` with `first_name: str | None`
  and `last_name: str | None`.
- New helper inside the script: `parse_owner_name(raw)` — duplicates
  the backend logic.
- `parse_row` calls it on the spreadsheet `Name` column when
  `_is_real_name(raw)` is true; otherwise both stay `None`.
- `build_create_payload` sends
  `owner_first_name` + `owner_last_name` + `phone_number` (all three or
  none, as today). `owner_last_name = ""` is valid (single-token
  names).
- Docstring "Behavior" section updated to describe the comma rule.

## Testing

### Unit (backend)

- `parse_owner_name`:
  - `"Doe, John"` → `("Doe", "John")` (first in front of comma)
  - `"  Doe ,  John  "` → `("Doe", "John")` (whitespace trimmed)
  - `"John Smith"` → `("John", "Smith")`
  - `"Mary Jane Watson"` → `("Mary", "Jane Watson")`
  - `"Cher"` → `("Cher", "")`
  - `""` / `"   "` → `("", "")`
  - `"a, b, c"` → `("a", "b, c")` (first comma only)
- `OwnerRepository.resolve_or_create`: new owner inserts; existing
  triple returns the same row; differing last_name creates a new row.

### Migration

- Fixture with rows
  `["John Smith", "Mary Jane Watson", "Cher", ""]` → expected splits
  applied; `name` column dropped.

### API

- `POST /discs` with split owner fields creates an owner and links it.
- `POST /discs` rejects partial owner fields (validator).
- `GET /me/discs` returns `notes: null` even when stored value is
  non-null.
- `GET /me/wishlist` returns the user-written `notes`.
- `POST /me/wishlist` with `notes` round-trips.

### Frontend

- `parseOwnerName` mirrors the backend cases.
- AdminDiscFormPage submits `owner_first_name`/`owner_last_name`/
  `phone_number` together.
- MyWishlistPage submits `notes`.

### Import script

- `"Smith, John"` posts `owner_first_name="Smith"`,
  `owner_last_name="John"`.
- `"John Smith"` posts `owner_first_name="John"`,
  `owner_last_name="Smith"`.
- `"Cher"` posts `owner_first_name="Cher"`, `owner_last_name=""`.
- `"?"` / blank posts no owner fields (ownerless disc).

## Open Risks

- **Names with internal commas that aren't separators.** E.g. company
  names like `"Acme, Inc"` would be parsed as `first="Acme"`,
  `last="Inc"`. The owner field is for individuals, so this is
  unlikely; admins can re-edit if it occurs.
