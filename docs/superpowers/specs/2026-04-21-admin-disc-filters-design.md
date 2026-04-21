# Admin Disc List Filters & Status Controls — Design

**Goal:** Add is_found/is_returned/owner_name filters to the admin disc list, enrich disc cards with interactive found and returned controls, and allow admins to mark wishlist discs as found.

**Architecture:** Backend adds three optional query params to the existing `GET /discs` admin path; `DiscRepository.list_all` and `count_all` apply them as WHERE clauses. Frontend adds a filter bar (admin-only) and interactive status controls on each disc card. No new endpoints, no schema changes — `DiscOut` and `DiscUpdate` already include all required fields.

**Tech Stack:** FastAPI, SQLAlchemy async (ilike), React, TanStack Query, existing `useListDiscs` hook and `updateDisc` mutation.

---

## Backend — DiscRepository

`list_all(*, page, page_size)` and `count_all()` gain three optional keyword params:

```python
async def list_all(
    self,
    *,
    page: int = 1,
    page_size: int = 50,
    is_found: bool | None = None,
    is_returned: bool | None = None,
    owner_name: str | None = None,
) -> list[Disc]:
```

Each param is appended to the WHERE clause only when not `None`:
- `is_found`: `Disc.is_found == is_found`
- `is_returned`: `Disc.is_returned == is_returned`
- `owner_name`: `Disc.owner_name.ilike(f"%{owner_name}%")` — case-insensitive substring match

`count_all` receives the same params and applies the same filters to the COUNT query.

The non-admin path (`list_by_phones`, `count_by_phones`) is unchanged.

---

## Backend — GET /discs endpoint

The admin branch of `listDiscs` accepts three new optional query params:

```python
is_found: bool | None = Query(default=None)
is_returned: bool | None = Query(default=None)
owner_name: str | None = Query(default=None)
```

These are forwarded to `repo.list_all(...)` and `repo.count_all(...)`. The non-admin branch ignores them entirely.

---

## Frontend — Filter Bar (admin only)

A filter bar renders above the disc list only when the current user `is_admin`. It contains three controls:

1. **Found** — `<select>`: options `All | Found | Not found` → maps to `is_found=undefined | true | false`
2. **Returned** — `<select>`: options `All | Returned | Not returned` → maps to `is_returned=undefined | true | false`
3. **Owner name** — `<input type="text">`: debounced 300ms, maps to `owner_name=value` (empty string = omit param)

Changing any filter resets pagination to page 1. Filter state is local React state; values are passed as query params to `useListDiscs()`.

---

## Frontend — Disc Card Enrichment (admin only)

When the current user is admin, each disc card gains two interactive controls:

### is_found toggle
A clickable badge displayed on each card:
- `is_found=true` → green "Found" badge
- `is_found=false` → gray "Not found" badge

Clicking the badge calls `PATCH /discs/{disc_id}` with `{ is_found: !current }` via the existing `updateDisc` mutation. On success, invalidate the disc list query so the card reflects the new state.

### is_returned checkbox
A checkbox next to the "Waiting for pickup" / "Returned" status area:
- Checked = `is_returned=true`
- Unchecked = `is_returned=false`

Clicking calls `PATCH /discs/{disc_id}` with `{ is_returned: !current }`. On success, invalidate the disc list query.

Both controls are only rendered for admin users. Regular users see the existing read-only status badge.

---

## Testing

- `test_discs.py`: `list_all` with `is_found=True` excludes wishlist discs; `is_found=False` returns only wishlist discs; `owner_name="alice"` returns only matching; combined filters work; no params returns all.
- `test_discs.py`: `GET /discs?is_found=false` as admin returns wishlist discs; `GET /discs?owner_name=alice` filters correctly; non-admin cannot use filter params (params ignored, still returns only their found discs).
- Frontend: filter bar only renders for admins; changing a filter resets to page 1; is_found toggle calls correct PATCH; is_returned checkbox calls correct PATCH.
