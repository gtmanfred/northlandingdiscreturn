# Disc ID Column Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every disc row in the `Current` sheet a stable uuid in column `K` so imports update discs by id instead of a fuzzy field match, and create discs using the id the spreadsheet supplies.

**Architecture:** `parse_current_sheet` reads column `K` into `ParsedDiscRow.disc_id`. A single resolver function decides create / create-with-id / update per row, and both `plan_import` (preview) and `apply_import` (write) call it, so the preview can never disagree with the apply. Rows with an empty `K` keep today's fuzzy `find_by_import_key` behavior, so nothing regresses before the backfill runs. A backfill service reads existing disc ids out of the database and stamps them into the sheet.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, openpyxl, pytest (`asyncio_mode = auto`), teststack for a throwaway Postgres; React 18 + TypeScript + vitest on the frontend.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-05-disc-id-column-design.md`. Read it before starting.
- No database schema change. No alembic migration. `discs.id` values already in the database are never rewritten.
- Only the `Current` sheet gets an ID column. `No Number`, `Returned`, `Hopefuls` are untouched.
- `scripts/import_discs.py` (the standalone POST-per-row script) is **not** modified.
- Column layout of `Current`: rows 1–3 are title / subtitle / header, data starts at row 4. `A`–`J` = Name, Phone, Mfr, Model, Color, Other, Code, Date found, Date returned, Date contacted. **`K` = `ID`** (frozen literal uuid). **`L` = `ID gen`** (formula helper, ignored by all code).
- Column index constants are 0-based when indexing a `values_only` row tuple (`K` = index 10) and 1-based in `openpyxl` `ws.cell()` calls (`K` = column 11). Do not mix them up.
- Exact error strings, used by both code and tests:
  - `"invalid ID"`
  - `"ID is a live formula — freeze with Paste Special > Values"` (em dash, not hyphen)
  - `"duplicate ID in sheet"`
- Exact warning string format: `f"possible duplicate — new ID but matches existing disc {disc.id}"` (em dash).
- Backend tests run from `backend/`: `teststack run tests` — or `teststack run tests -- -k <name> -v` for one test. Frontend tests: `npx vitest run <path>` from `frontend/`.
- Every task ends with a commit. Conventional Commits style, matching existing history (`feat(import): ...`, `test: ...`, `docs: ...`).

---

### Task 1: Repository accepts an explicit disc id

**Files:**
- Modify: `backend/app/repositories/disc.py:14-38` (`DiscRepository.create`)
- Test: `backend/tests/test_discs.py` (append at end of file)

**Interfaces:**
- Consumes: nothing.
- Produces: `DiscRepository.create(*, manufacturer: str, name: str, colors: list[str], input_date: date, owner_id: uuid.UUID | None = None, is_clear: bool = False, is_found: bool = True, notes: str | None = None, id: uuid.UUID | None = None) -> Disc`. When `id` is `None` the model default `uuid.uuid4` applies, so all existing callers are unaffected.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_discs.py`:

```python
async def test_repo_create_accepts_explicit_id(db):
    import uuid as _uuid
    from datetime import date as _date
    from app.repositories.disc import DiscRepository

    wanted = _uuid.uuid4()
    repo = DiscRepository(db)
    disc = await repo.create(
        manufacturer="Innova",
        name="Teebird",
        colors=["white"],
        input_date=_date(2026, 6, 1),
        id=wanted,
    )
    assert disc.id == wanted
    assert (await repo.get_by_id(wanted)) is not None


async def test_repo_create_without_id_generates_one(db):
    from datetime import date as _date
    from app.repositories.disc import DiscRepository

    repo = DiscRepository(db)
    disc = await repo.create(
        manufacturer="Innova",
        name="Roc",
        colors=["blue"],
        input_date=_date(2026, 6, 1),
    )
    assert disc.id is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && teststack run tests -- -k test_repo_create_accepts_explicit_id -v`
Expected: FAIL — `TypeError: create() got an unexpected keyword argument 'id'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/repositories/disc.py`, add the parameter and pass it through. `Disc(id=None, ...)` would override the column default with `None`, so only set it when provided:

```python
    async def create(
        self,
        *,
        manufacturer: str,
        name: str,
        colors: list[str],
        input_date: date,
        owner_id: uuid.UUID | None = None,
        is_clear: bool = False,
        is_found: bool = True,
        notes: str | None = None,
        id: uuid.UUID | None = None,
    ) -> Disc:
        kwargs = {} if id is None else {"id": id}
        disc = Disc(
            manufacturer=manufacturer,
            name=name,
            colors=colors,
            input_date=input_date,
            owner_id=owner_id,
            is_clear=is_clear,
            is_found=is_found,
            notes=notes,
            **kwargs,
        )
        self.db.add(disc)
        await self.db.flush()
        await self.db.refresh(disc)
        return disc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && teststack run tests -- -k "test_repo_create" -v`
Expected: PASS, both tests.

Run the whole disc suite to prove no caller broke: `teststack run tests -- -k "disc" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/disc.py backend/tests/test_discs.py
git commit -m "feat(discs): allow creating a disc with an explicit id"
```

---

### Task 2: Parser reads column K

**Files:**
- Modify: `backend/app/services/disc_import.py:1-113` (imports, `ParsedDiscRow`, `parse_current_sheet`) and `:190-222` (`row_to_dict`, `row_from_dict`)
- Test: `backend/tests/test_disc_import.py` (append tests; modify the `_make_sheet` helper)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ParsedDiscRow.disc_id: uuid.UUID | None` (new field, declared **after** `returned_date` and **before** `error`, so the existing `error=...` keyword usage keeps working — but declare it with a default `= None` and keep `error: str | None = None` last).
  - Module constants `ID_COLUMN_INDEX = 10`, `ID_COLUMN_NUMBER = 11`, `INVALID_ID_ERROR`, `FORMULA_ID_ERROR`, `DUPLICATE_ID_ERROR`.
  - `row_to_dict(r)` emits `"disc_id": str(r.disc_id) if r.disc_id else None`; `row_from_dict(d)` reads it back with `uuid.UUID(...)`, tolerating a missing key so staging rows written before this change still load.

- [ ] **Step 1: Write the failing tests**

First update the existing helper in `backend/tests/test_disc_import.py` so tests can supply an ID cell and a formula cell. Replace `_make_sheet` with:

```python
def _make_sheet(data_rows, *, id_header=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Current"
    ws.append(["North Landing Discs Database"])
    ws.append(["Sorted by ...", None, None, None, None, None, "Code: ..."])
    header = ["Name", "Phone", "Mfr", "Model", "Color", "Other",
              "Code", "Date found", "Date retuned", "Date contacted"]
    if id_header:
        header.append("ID")
    ws.append(header)
    for r in data_rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

Existing rows in that file pass 10-element lists, which still work — the 11th cell is simply absent.

Now append these tests:

```python
def test_parse_reads_disc_id_from_column_k():
    known = uuid.uuid4()
    data = _make_sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", None, None,
         _date(2026, 6, 6), None, None, str(known)],
    ])
    row = parse_current_sheet(data)[0]
    assert row.disc_id == known
    assert row.error is None


def test_parse_blank_id_is_none():
    data = _make_sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", None, None,
         _date(2026, 6, 6), None, None, "   "],
    ])
    row = parse_current_sheet(data)[0]
    assert row.disc_id is None
    assert row.error is None


def test_parse_malformed_id_is_an_error():
    data = _make_sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", None, None,
         _date(2026, 6, 6), None, None, "not-a-uuid"],
    ])
    row = parse_current_sheet(data)[0]
    assert row.disc_id is None
    assert row.error == "invalid ID"


def test_parse_live_formula_in_id_is_an_error():
    data = _make_sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", None, None,
         _date(2026, 6, 6), None, None, "=L4"],
    ])
    row = parse_current_sheet(data)[0]
    assert row.disc_id is None
    assert row.error == "ID is a live formula — freeze with Paste Special > Values"


def test_parse_duplicate_id_errors_every_participating_row():
    shared = str(uuid.uuid4())
    data = _make_sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", None, None,
         _date(2026, 6, 6), None, None, shared],
        ["Bob Roe", "404-951-8882", "Innova", "Roc", "blue", None, None,
         _date(2026, 6, 7), None, None, shared],
        ["Sue Poe", "404-951-8883", "Innova", "Leopard", "red", None, None,
         _date(2026, 6, 8), None, None, str(uuid.uuid4())],
    ])
    rows = parse_current_sheet(data)
    assert rows[0].error == "duplicate ID in sheet"
    assert rows[1].error == "duplicate ID in sheet"
    assert rows[2].error is None


def test_parse_ignores_helper_column_l():
    known = uuid.uuid4()
    data = _make_sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", None, None,
         _date(2026, 6, 6), None, None, str(known), "=IF($K4<>\"\",$K4,\"x\")"],
    ])
    row = parse_current_sheet(data)[0]
    assert row.disc_id == known
    assert row.error is None


def test_row_dict_round_trip_carries_disc_id():
    known = uuid.uuid4()
    r = ParsedDiscRow(
        row_number=4, first_name="Jane", last_name="Doe", phone="+15551234567",
        manufacturer="Innova", model="Teebird", colors=["white"], notes=None,
        input_date=_date(2026, 6, 1), returned=False, returned_date=None,
        disc_id=known,
    )
    assert row_from_dict(row_to_dict(r)) == r


def test_row_from_dict_tolerates_legacy_rows_without_disc_id():
    legacy = {
        "row_number": 4, "first_name": "Jane", "last_name": "Doe",
        "phone": "+15551234567", "manufacturer": "Innova", "model": "Teebird",
        "colors": ["white"], "notes": None, "input_date": "2026-06-01",
        "returned": False, "returned_date": None, "error": None,
    }
    assert row_from_dict(legacy).disc_id is None
```

Add to that file's imports:

```python
import uuid
from app.services.disc_import import (
    parse_current_sheet, ParsedDiscRow, apply_import, ImportSummary,
    row_to_dict, row_from_dict,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && teststack run tests -- -k "disc_id or live_formula or helper_column" -v`
Expected: FAIL — `TypeError: ParsedDiscRow.__init__() got an unexpected keyword argument 'disc_id'` and `AttributeError`/assert failures on `row.disc_id`.

- [ ] **Step 3: Write the implementation**

In `backend/app/services/disc_import.py`, add `import uuid` next to the existing imports and these constants under `HEADER_KEYWORD`:

```python
ID_COLUMN_INDEX = 10   # 0-based index into a values_only row tuple: column K
ID_COLUMN_NUMBER = 11  # 1-based openpyxl column number: column K
INVALID_ID_ERROR = "invalid ID"
FORMULA_ID_ERROR = "ID is a live formula — freeze with Paste Special > Values"
DUPLICATE_ID_ERROR = "duplicate ID in sheet"
```

Add the field to the dataclass (note ordering — defaults must stay trailing):

```python
@dataclass
class ParsedDiscRow:
    row_number: int
    first_name: str
    last_name: str
    phone: str | None
    manufacturer: str
    model: str
    colors: list[str]
    notes: str | None
    input_date: date | None
    returned: bool
    returned_date: date | None
    disc_id: uuid.UUID | None = None
    error: str | None = None
```

Add two helpers above `parse_current_sheet`:

```python
def _cell(grid, row_index: int, col_index: int):
    """Value at a 0-based grid position, or None when the row/column is short."""
    if row_index < 0 or row_index >= len(grid):
        return None
    row = grid[row_index]
    return row[col_index] if col_index < len(row) else None


def _parse_disc_id(value, formula) -> tuple[uuid.UUID | None, str | None]:
    """(disc_id, error) for one ID cell. `formula` is the un-evaluated cell content."""
    if isinstance(formula, str) and formula.startswith("="):
        return None, FORMULA_ID_ERROR
    text = str(value).strip() if value is not None else ""
    if not text:
        return None, None
    try:
        return uuid.UUID(text), None
    except (ValueError, AttributeError, TypeError):
        return None, INVALID_ID_ERROR
```

The formula check must consult the un-evaluated grid: the existing `data_only=True` load returns Excel's *cached* value for a formula cell, which looks like a perfectly good uuid. So load the workbook twice in `parse_current_sheet`:

```python
def parse_current_sheet(file_bytes: bytes) -> list[ParsedDiscRow]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    if SHEET_NAME not in wb.sheetnames:
        raise ValueError("Current sheet not found")
    ws = wb[SHEET_NAME]
    grid = list(ws.iter_rows(values_only=True))

    formula_wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
    formula_grid = list(formula_wb[SHEET_NAME].iter_rows(values_only=True))
```

Leave the header-detection block as it is. Inside the row loop, keep the existing unpacking of the first ten cells but stop truncating the row, then read the ID. Replace the two lines

```python
        cells = list(r) + [None] * (10 - len(r))
        name, phone, mfr, model, color, other, code, found, returned_dt, _ = cells[:10]
```

with

```python
        cells = list(r) + [None] * (11 - len(r))
        name, phone, mfr, model, color, other, code, found, returned_dt, _ = cells[:10]
        disc_id, id_error = _parse_disc_id(
            cells[ID_COLUMN_INDEX],
            _cell(formula_grid, offset - 1, ID_COLUMN_INDEX),
        )
```

`offset` is the 1-based Excel row number, so `offset - 1` is its 0-based grid index.

The existing `error` assignment becomes `id_error`-aware — an ID problem is reported ahead of the date problem, because a row with a broken ID cannot be safely matched at all:

```python
        error = id_error
        if error is None and input_date is None:
            error = "missing or invalid Date found"
```

Add `disc_id=disc_id,` to the `ParsedDiscRow(...)` construction (before `error=error`).

After the loop, before `return rows`, flag duplicates:

```python
    by_id: dict[uuid.UUID, list[ParsedDiscRow]] = {}
    for row in rows:
        if row.disc_id is not None:
            by_id.setdefault(row.disc_id, []).append(row)
    for group in by_id.values():
        if len(group) > 1:
            for row in group:
                row.disc_id = None
                row.error = DUPLICATE_ID_ERROR
    return rows
```

Clearing `disc_id` on a duplicate keeps a later resolver from ever acting on an ambiguous id, even if some caller ignores `error`.

Finally, carry the field through the staging serializers:

```python
def row_to_dict(r: ParsedDiscRow) -> dict:
    return {
        "row_number": r.row_number,
        "first_name": r.first_name,
        "last_name": r.last_name,
        "phone": r.phone,
        "manufacturer": r.manufacturer,
        "model": r.model,
        "colors": r.colors,
        "notes": r.notes,
        "input_date": r.input_date.isoformat() if r.input_date else None,
        "returned": r.returned,
        "returned_date": r.returned_date.isoformat() if r.returned_date else None,
        "disc_id": str(r.disc_id) if r.disc_id is not None else None,
        "error": r.error,
    }


def row_from_dict(d: dict) -> ParsedDiscRow:
    raw_id = d.get("disc_id")
    return ParsedDiscRow(
        row_number=d["row_number"],
        first_name=d["first_name"],
        last_name=d["last_name"],
        phone=d["phone"],
        manufacturer=d["manufacturer"],
        model=d["model"],
        colors=d["colors"],
        notes=d["notes"],
        input_date=date.fromisoformat(d["input_date"]) if d["input_date"] else None,
        returned=d["returned"],
        returned_date=date.fromisoformat(d["returned_date"]) if d["returned_date"] else None,
        disc_id=uuid.UUID(raw_id) if raw_id else None,
        error=d["error"],
    )
```

`d.get("disc_id")` (not `d["disc_id"]`) is what makes pending `import_staging` rows created before this deploy still load.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && teststack run tests -- -k "disc_import or disc_plan or import_staging" -v`
Expected: PASS, including every pre-existing parser test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/disc_import.py backend/tests/test_disc_import.py
git commit -m "feat(import): parse ID column from the Current sheet"
```

---

### Task 3: Identity resolver and ID-aware apply

**Files:**
- Modify: `backend/app/services/disc_import.py` (add `_resolve`; rewrite the lookup block in `apply_import:140-188`)
- Test: `backend/tests/test_disc_import.py` (append)

**Interfaces:**
- Consumes: `ParsedDiscRow.disc_id` (Task 2), `DiscRepository.create(..., id=)` (Task 1).
- Produces: `async def _resolve(row: ParsedDiscRow, disc_repo: DiscRepository) -> tuple[str, Disc | None, Disc | None]` returning `(action, existing, drift)` where `action` is one of the module constants `ACTION_CREATE = "create"`, `ACTION_CREATE_WITH_ID = "create_with_id"`, `ACTION_UPDATE = "update"`. `existing` is the disc to update (only for `update`); `drift` is a fuzzy-key match found while creating with a supplied id (only for `create_with_id`, else `None`). Task 4 consumes this same function.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_disc_import.py`. Reuse the `_row(**kw)` helper already defined at line 113 of that file — `ParsedDiscRow.disc_id` defaults to `None`, so `_row()` keeps working unchanged and `_row(disc_id=...)` sets it. Match the file's existing style: it decorates every async test with `@pytest.mark.asyncio`.

```python
@pytest.mark.asyncio
async def test_apply_creates_disc_with_the_sheet_id(db):
    wanted = uuid.uuid4()
    summary = await apply_import([_row(disc_id=wanted)], db)
    assert summary.created == 1
    disc = await DiscRepository(db).get_by_id(wanted)
    assert disc is not None
    assert disc.name == "Teebird"


@pytest.mark.asyncio
async def test_apply_updates_the_disc_named_by_the_id(db):
    wanted = uuid.uuid4()
    await apply_import([_row(disc_id=wanted)], db)
    summary = await apply_import([_row(disc_id=wanted, notes="changed")], db)
    assert summary.created == 0
    assert summary.updated == 1
    disc = await DiscRepository(db).get_by_id(wanted)
    assert disc.notes == "changed"


@pytest.mark.asyncio
async def test_id_match_beats_a_conflicting_fuzzy_match(db):
    """Row's fields match disc B, but its ID names disc A. A is updated, B is not."""
    id_a = uuid.uuid4()
    repo = DiscRepository(db)
    disc_a = await repo.create(
        manufacturer="Latitude 64", name="River", colors=["green"],
        input_date=_date(2020, 1, 1), notes="a", id=id_a,
    )
    disc_b = await repo.create(
        manufacturer="Innova", name="Teebird", colors=["white"],
        input_date=_date(2026, 6, 1), notes="b",
    )
    summary = await apply_import([_row(disc_id=id_a, notes="from sheet")], db)
    assert summary.updated == 1
    assert summary.created == 0
    assert (await repo.get_by_id(disc_a.id)).notes == "from sheet"
    assert (await repo.get_by_id(disc_b.id)).notes == "b"


@pytest.mark.asyncio
async def test_changed_fields_still_update_when_the_id_is_stable(db):
    """The whole point: edit a matched field and the disc updates instead of duplicating."""
    wanted = uuid.uuid4()
    await apply_import([_row(disc_id=wanted)], db)
    summary = await apply_import([_row(disc_id=wanted, colors=["red"])], db)
    assert summary.created == 0
    assert summary.updated == 1
    discs = (await db.execute(select(Disc))).scalars().all()
    assert len(discs) == 1
    assert discs[0].colors == ["red"]


@pytest.mark.asyncio
async def test_blank_id_still_uses_the_fuzzy_key(db):
    await apply_import([_row()], db)
    summary = await apply_import([_row(notes="changed")], db)
    assert summary.created == 0
    assert summary.updated == 1


@pytest.mark.asyncio
async def test_reimport_of_a_known_id_sends_no_sms(db):
    wanted = uuid.uuid4()
    await apply_import([_row(disc_id=wanted)], db)
    before = len((await db.execute(select(SMSJob))).scalars().all())
    await apply_import([_row(disc_id=wanted, notes="changed")], db)
    after = len((await db.execute(select(SMSJob))).scalars().all())
    assert after == before


@pytest.mark.asyncio
async def test_apply_skips_rows_with_id_errors(db):
    summary = await apply_import([_row(disc_id=None, error="invalid ID")], db)
    assert summary.created == 0
    assert summary.errors == [{"row": 4, "reason": "invalid ID"}]
    assert (await db.execute(select(Disc))).scalars().all() == []
```

Add `from app.models.disc import Disc` to that file's imports if it is not already there.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && teststack run tests -- -k "sheet_id or conflicting_fuzzy or id_is_stable or known_id" -v`
Expected: FAIL — discs get server-generated ids, so `get_by_id(wanted)` returns `None`; the stable-id test creates a second disc instead of updating.

- [ ] **Step 3: Write the implementation**

Add the action constants next to the other module constants in `backend/app/services/disc_import.py`:

```python
ACTION_CREATE = "create"
ACTION_CREATE_WITH_ID = "create_with_id"
ACTION_UPDATE = "update"
```

Add the resolver above `apply_import`:

```python
async def _resolve(row: ParsedDiscRow, disc_repo: DiscRepository):
    """Decide what this row does. Returns (action, existing, drift).

    An ID that names a live disc wins over any fuzzy match. An ID the database
    does not know creates that exact id; `drift` then reports a fuzzy match, which
    means the id probably changed under a row that already exists (an unfrozen
    formula) rather than the row being genuinely new.
    """
    if row.disc_id is not None:
        existing = await disc_repo.get_by_id(row.disc_id)
        if existing is not None:
            return ACTION_UPDATE, existing, None
        drift = await disc_repo.find_by_import_key(
            input_date=row.input_date,
            manufacturer=row.manufacturer,
            name=row.model,
            colors=row.colors,
            phone=row.phone,
        )
        return ACTION_CREATE_WITH_ID, None, drift

    existing = await disc_repo.find_by_import_key(
        input_date=row.input_date,
        manufacturer=row.manufacturer,
        name=row.model,
        colors=row.colors,
        phone=row.phone,
    )
    if existing is not None:
        return ACTION_UPDATE, existing, None
    return ACTION_CREATE, None, None
```

In `apply_import`, replace the `existing = await disc_repo.find_by_import_key(...)` call and the `if existing is None:` branch head with the resolver, and pass the id on create. The owner-resolution block above it is unchanged:

```python
        action, existing, _drift = await _resolve(row, disc_repo)

        if existing is None:
            disc = await disc_repo.create(
                manufacturer=row.manufacturer,
                name=row.model,
                colors=row.colors,
                input_date=row.input_date,
                owner_id=owner_id,
                notes=row.notes,
                id=row.disc_id if action == ACTION_CREATE_WITH_ID else None,
            )
```

The rest of that branch (the `if row.returned:` / `else:` welcome and heads-up block, `summary.created += 1`) and the whole `else:` update branch stay exactly as they are.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && teststack run tests -- -k "disc_import or disc_plan or import_endpoints" -v`
Expected: PASS, including all pre-existing import tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/disc_import.py backend/tests/test_disc_import.py
git commit -m "feat(import): match discs by spreadsheet ID before fuzzy key"
```

---

### Task 4: Preview reports the same actions plus a drift warning

**Files:**
- Modify: `backend/app/services/disc_import.py` (`ImportPlan.to_dict:275-292`, `plan_import:295-329`)
- Test: `backend/tests/test_disc_plan.py` (modify `_row` helper, append tests)

**Interfaces:**
- Consumes: `_resolve`, `ACTION_CREATE_WITH_ID` (Task 3).
- Produces: every entry of `ImportPlan.created` gains `"duplicate_warning": str | None`. `plan.to_dict()["counts"]` gains `"possible_duplicates": int`. Existing keys (`will_notify`, `skip_reason`, `diffs`, `unchanged`, `errors`, `created`/`updated`/`errors` counts) are unchanged. Task 8 renders these.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_disc_plan.py`, add `disc_id=None` to the `_row` helper's `base` dict so it keeps constructing valid rows, and add `import uuid` plus `from datetime import date as _date` (already present) at the top. Then append:

```python
async def test_plan_created_entries_carry_no_warning_by_default(db):
    plan = await plan_import([_row()], db)
    d = plan.to_dict()
    assert d["created"][0]["duplicate_warning"] is None
    assert d["counts"]["possible_duplicates"] == 0


async def test_plan_warns_when_a_new_id_matches_an_existing_disc(db):
    """Unfrozen formula: same disc, brand-new id. Flag it before it duplicates."""
    await apply_import([_row()], db)
    existing = (await db.execute(select(Disc))).scalars().one()
    plan = await plan_import([_row(disc_id=uuid.uuid4())], db)
    d = plan.to_dict()
    assert d["counts"]["created"] == 1
    assert d["counts"]["possible_duplicates"] == 1
    assert d["created"][0]["duplicate_warning"] == (
        f"possible duplicate — new ID but matches existing disc {existing.id}"
    )


async def test_plan_classifies_an_id_match_as_updated(db):
    known = uuid.uuid4()
    await apply_import([_row(disc_id=known)], db)
    plan = await plan_import([_row(disc_id=known, notes="changed")], db)
    d = plan.to_dict()
    assert d["counts"]["updated"] == 1
    assert d["counts"]["created"] == 0
    assert d["updated"][0]["diffs"] == [{"field": "notes", "old": "x", "new": "changed"}]


async def test_plan_unknown_id_with_no_fuzzy_match_is_a_clean_create(db):
    plan = await plan_import([_row(disc_id=uuid.uuid4())], db)
    d = plan.to_dict()
    assert d["counts"]["created"] == 1
    assert d["counts"]["possible_duplicates"] == 0


async def test_plan_matches_apply_for_id_rows(db):
    """Preview and apply must never disagree."""
    known = uuid.uuid4()
    rows = [_row(disc_id=known)]
    first_plan = (await plan_import(rows, db)).to_dict()
    first_apply = await apply_import(rows, db)
    assert first_plan["counts"]["created"] == first_apply.created

    rows2 = [_row(disc_id=known, notes="changed")]
    second_plan = (await plan_import(rows2, db)).to_dict()
    second_apply = await apply_import(rows2, db)
    assert second_plan["counts"]["updated"] == second_apply.updated
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && teststack run tests -- -k "duplicate_warning or possible_duplicates or new_id_matches or id_match_as_updated" -v`
Expected: FAIL — `KeyError: 'duplicate_warning'` and `KeyError: 'possible_duplicates'`.

- [ ] **Step 3: Write the implementation**

In `backend/app/services/disc_import.py`, add the warning builder next to `_notify_status`:

```python
def _duplicate_warning(drift) -> str | None:
    """Set when a sheet-supplied ID is unknown but the row's fields match a live disc."""
    if drift is None:
        return None
    return f"possible duplicate — new ID but matches existing disc {drift.id}"
```

Add the count to `ImportPlan.to_dict()`'s `counts` dict (leave every other key alone):

```python
                "will_notify": sum(1 for c in self.created if c["will_notify"]),
                "possible_duplicates": sum(
                    1 for c in self.created if c["duplicate_warning"]
                ),
```

Rewrite the body of `plan_import`'s loop to use the resolver:

```python
async def plan_import(rows: list[ParsedDiscRow], db: AsyncSession) -> ImportPlan:
    """Read-only classification of what an import would do. No writes, no SMS."""
    disc_repo = DiscRepository(db)
    plan = ImportPlan()
    for row in rows:
        if row.error or row.input_date is None:
            plan.errors.append(
                {"row": row_to_dict(row), "reason": row.error or "no date found"}
            )
            continue
        action, existing, drift = await _resolve(row, disc_repo)
        label = {"row_number": row.row_number, **_disc_label(row)}
        if existing is None:
            will_notify, skip_reason = _notify_status(row)
            plan.created.append({
                **label,
                "will_notify": will_notify,
                "skip_reason": skip_reason,
                "duplicate_warning": _duplicate_warning(drift),
            })
        else:
            diffs = _plan_diffs(existing, row)
            if diffs:
                plan.updated.append({**label, "diffs": diffs})
            else:
                plan.unchanged += 1
    return plan
```

`action` is unused in this function's body but keep the three-tuple unpack — it documents the shared contract with `apply_import`, and lint does not flag it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && teststack run tests -- -k "disc_plan or import_endpoints" -v`
Expected: PASS.

Then run the whole backend suite — the plan dict is a public API shape:
Run: `cd backend && teststack run tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/disc_import.py backend/tests/test_disc_plan.py
git commit -m "feat(import): warn in preview when a new ID matches an existing disc"
```

---

### Task 5: Export writes ids back into column K

**Files:**
- Modify: `backend/app/services/disc_export.py:4-7` (`DISC_EXPORT_COLUMNS`), `backend/app/routers/discs.py:131-143` (the export row builder)
- Test: `backend/tests/test_disc_export.py` (modify `test_columns_order` and `test_build_workbook_roundtrip`), `backend/tests/test_discs.py` (append an endpoint test)

**Interfaces:**
- Consumes: nothing.
- Produces: `DISC_EXPORT_COLUMNS` ends with `"ID"`, making it column `K` — the same position the `Current` sheet uses. Export rows include `"ID": str(d.id)`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_disc_export.py`, update the existing assertions:

```python
def test_columns_order():
    assert DISC_EXPORT_COLUMNS == [
        "Name", "Phone", "Mfr", "Model", "Color", "Other",
        "Code", "Date found", "Date returned", "Date contacted", "ID",
    ]


def test_build_workbook_roundtrip():
    rows = [{
        "Name": "Jane Doe", "Phone": "+15551234567", "Mfr": "Innova",
        "Model": "Teebird", "Color": "white", "Other": "no prev",
        "Code": "", "Date found": date(2026, 6, 1),
        "Date returned": None, "Date contacted": date(2026, 6, 3),
        "ID": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
    }]
    data = build_current_sheet_workbook(rows)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    grid = list(ws.iter_rows(values_only=True))
    header = grid[1]
    assert list(header) == DISC_EXPORT_COLUMNS
    first = dict(zip(header, grid[2]))
    assert first["Name"] == "Jane Doe"
    assert first["Date found"] == date(2026, 6, 1)
    assert first["Date returned"] is None
    assert first["Date contacted"] == date(2026, 6, 3)
    assert first["ID"] == "3f2504e0-4f89-41d3-9a0c-0305e82c3301"


def test_id_is_written_as_text_not_a_formula():
    rows = [{"ID": "3f2504e0-4f89-41d3-9a0c-0305e82c3301"}]
    data = build_current_sheet_workbook(rows)
    ws = openpyxl.load_workbook(io.BytesIO(data), data_only=False).active
    cell = ws.cell(row=3, column=11)
    assert cell.value == "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    assert not str(cell.value).startswith("=")
```

The exported ID must be a literal so a re-downloaded sheet needs no freeze for its existing rows.

Append to `backend/tests/test_discs.py` an end-to-end check that the value is a real disc id. `admin_headers(user_id)` and `make_admin(db, ...)` are module-level helpers in that file (around lines 194–200), not fixtures — the existing export test at ~line 575 uses exactly this pattern:

```python
async def test_export_includes_disc_id_column(db, client):
    import io, openpyxl

    admin = await make_admin(db, name="IdAdmin", email="id@x.com", google_id="g-id")
    disc = await DiscRepository(db).create(
        manufacturer="Innova", name="Teebird", colors=["white"],
        input_date=date(2026, 6, 1),
    )
    await db.flush()

    r = await client.get("/discs/export", headers=admin_headers(admin.id))
    assert r.status_code == 200
    grid = list(openpyxl.load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
    header = list(grid[1])
    assert header[10] == "ID"
    ids = {dict(zip(header, row))["ID"] for row in grid[2:]}
    assert str(disc.id) in ids
```

`make_admin` must use an email and `google_id` not already used elsewhere in the file, or the insert collides on a unique constraint. `date` and `DiscRepository` are already imported at the top of that file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && teststack run tests -- -k "export" -v`
Expected: FAIL — `assert DISC_EXPORT_COLUMNS == [...]` mismatch, and `header[10]` is `None`.

- [ ] **Step 3: Write the implementation**

`backend/app/services/disc_export.py`:

```python
DISC_EXPORT_COLUMNS = [
    "Name", "Phone", "Mfr", "Model", "Color", "Other",
    "Code", "Date found", "Date returned", "Date contacted", "ID",
]
```

Nothing else in that module changes — it already writes `row.get(col)` for each column, and `DATE_COLUMNS` does not include `"ID"`, so no date format is applied.

`backend/app/routers/discs.py`, in the `export_discs` row builder, add the final key:

```python
            "Date contacted": contacted,
            "ID": str(d.id),
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && teststack run tests -- -k "export" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/disc_export.py backend/app/routers/discs.py backend/tests/test_disc_export.py backend/tests/test_discs.py
git commit -m "feat(export): include disc ID column in the xlsx export"
```

---

### Task 6: Backfill service — pull real ids out of the database into the sheet

**Files:**
- Create: `backend/app/services/disc_id_backfill.py`
- Test: `backend/tests/test_disc_id_backfill.py`

**Interfaces:**
- Consumes: `parse_current_sheet`, `INVALID_ID_ERROR`, `FORMULA_ID_ERROR`, `DUPLICATE_ID_ERROR`, `ID_COLUMN_NUMBER`, `SHEET_NAME` (Task 2); `DiscRepository.find_by_import_key`.
- Produces:
  - `@dataclass BackfillReport` with fields `already_populated: int`, `matched: int`, `generated: int`, `skipped: list[dict]`, and method `as_dict() -> dict`.
  - `async def backfill_ids(file_bytes: bytes, db: AsyncSession, *, dry_run: bool = False) -> tuple[bytes | None, BackfillReport]`. Returns the rewritten workbook bytes, or `None` when `dry_run=True`.
  - Task 7 wraps this in a CLI.

The logic lives in the backend (not in `scripts/`) so it runs under the existing `db` test fixture. `scripts/backfill_disc_ids.py` stays a thin argparse + engine + file-IO wrapper.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_disc_id_backfill.py`:

```python
import io
import uuid
from datetime import date as _date

import openpyxl

from app.repositories.disc import DiscRepository
from app.services.disc_id_backfill import backfill_ids


def _sheet(data_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Current"
    ws.append(["North Landing Discs Database"])
    ws.append(["Sorted by ..."])
    ws.append(["Name", "Phone", "Mfr", "Model", "Color", "Other",
               "Code", "Date found", "Date retuned", "Date contacted", "ID"])
    for r in data_rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _ids(out_bytes):
    ws = openpyxl.load_workbook(io.BytesIO(out_bytes)).active
    return {r[0].row: r[0].value for r in ws.iter_rows(min_row=4, min_col=11, max_col=11)}


async def test_matched_row_receives_the_databases_id(db):
    disc = await DiscRepository(db).create(
        manufacturer="Innova", name="Teebird", colors=["white"],
        input_date=_date(2026, 6, 1),
    )
    data = _sheet([["?", None, "Innova", "Teebird", "white", None, None,
                    _date(2026, 6, 1), None, None, None]])
    out, report = await backfill_ids(data, db)
    assert _ids(out)[4] == str(disc.id)
    assert report.matched == 1
    assert report.generated == 0


async def test_unmatched_row_receives_a_fresh_uuid(db):
    data = _sheet([["?", None, "Innova", "Nothing", "pink", None, None,
                    _date(2026, 6, 1), None, None, None]])
    out, report = await backfill_ids(data, db)
    value = _ids(out)[4]
    assert uuid.UUID(value)
    assert report.generated == 1
    assert report.matched == 0


async def test_populated_id_is_never_modified(db):
    keep = str(uuid.uuid4())
    data = _sheet([["?", None, "Innova", "Teebird", "white", None, None,
                    _date(2026, 6, 1), None, None, keep]])
    out, report = await backfill_ids(data, db)
    assert _ids(out)[4] == keep
    assert report.already_populated == 1
    assert report.matched == 0
    assert report.generated == 0


async def test_dry_run_returns_no_bytes_but_a_full_report(db):
    data = _sheet([["?", None, "Innova", "Nothing", "pink", None, None,
                    _date(2026, 6, 1), None, None, None]])
    out, report = await backfill_ids(data, db, dry_run=True)
    assert out is None
    assert report.generated == 1


async def test_second_row_resolving_to_a_claimed_disc_is_left_blank(db):
    await DiscRepository(db).create(
        manufacturer="Innova", name="Teebird", colors=["white"],
        input_date=_date(2026, 6, 1),
    )
    row = ["?", None, "Innova", "Teebird", "white", None, None,
           _date(2026, 6, 1), None, None, None]
    out, report = await backfill_ids(_sheet([list(row), list(row)]), db)
    ids = _ids(out)
    assert ids[4] is not None
    assert ids[5] is None
    assert report.matched == 1
    assert [s["row"] for s in report.skipped] == [5]
    assert "already claimed" in report.skipped[0]["reason"]


async def test_rows_with_id_errors_are_skipped_not_overwritten(db):
    data = _sheet([["?", None, "Innova", "Teebird", "white", None, None,
                    _date(2026, 6, 1), None, None, "not-a-uuid"]])
    out, report = await backfill_ids(data, db)
    assert _ids(out)[4] == "not-a-uuid"
    assert [s["reason"] for s in report.skipped] == ["invalid ID"]


async def test_row_missing_a_date_still_gets_a_fresh_uuid(db):
    data = _sheet([["?", None, "Innova", "Teebird", "white", None, None,
                    None, None, None, None]])
    out, report = await backfill_ids(data, db)
    assert uuid.UUID(_ids(out)[4])
    assert report.generated == 1
```

The last test pins a deliberate decision: a row with no `Date found` cannot be fuzzy-matched, but it still deserves an id so the next import creates it with a stable identity (that import will report the missing date as a row error, as it does today).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && teststack run tests -- -k backfill -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.disc_id_backfill'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/disc_id_backfill.py`:

```python
"""Stamp stable ids into the Current sheet's ID column.

One-off reconciliation. Reads the database, writes only the spreadsheet: a row
that resolves to an existing disc gets that disc's real uuid, an unresolved row
gets a fresh uuid so the next import creates it with a stable identity. A cell
that already holds something is never touched.
"""

import io
import uuid
from dataclasses import dataclass, field

import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.disc import DiscRepository
from app.services.disc_import import (
    DUPLICATE_ID_ERROR,
    FORMULA_ID_ERROR,
    ID_COLUMN_NUMBER,
    INVALID_ID_ERROR,
    SHEET_NAME,
    parse_current_sheet,
)

ID_ERRORS = {INVALID_ID_ERROR, FORMULA_ID_ERROR, DUPLICATE_ID_ERROR}


@dataclass
class BackfillReport:
    already_populated: int = 0
    matched: int = 0
    generated: int = 0
    skipped: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "already_populated": self.already_populated,
            "matched": self.matched,
            "generated": self.generated,
            "skipped": self.skipped,
        }


async def backfill_ids(
    file_bytes: bytes,
    db: AsyncSession,
    *,
    dry_run: bool = False,
) -> tuple[bytes | None, BackfillReport]:
    rows = parse_current_sheet(file_bytes)
    disc_repo = DiscRepository(db)
    report = BackfillReport()

    # data_only=False keeps every other cell's formula intact on save.
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
    ws = wb[SHEET_NAME]

    claimed: set[uuid.UUID] = set()
    writes: list[tuple[int, str]] = []

    for row in rows:
        if row.disc_id is not None:
            report.already_populated += 1
            claimed.add(row.disc_id)
            continue
        if row.error in ID_ERRORS:
            report.skipped.append({"row": row.row_number, "reason": row.error})
            continue

        existing = None
        if row.input_date is not None:
            existing = await disc_repo.find_by_import_key(
                input_date=row.input_date,
                manufacturer=row.manufacturer,
                name=row.model,
                colors=row.colors,
                phone=row.phone,
            )

        if existing is None:
            new_id = uuid.uuid4()
            report.generated += 1
        elif existing.id in claimed:
            report.skipped.append({
                "row": row.row_number,
                "reason": f"resolved disc {existing.id} already claimed by an earlier row",
            })
            continue
        else:
            new_id = existing.id
            report.matched += 1

        claimed.add(new_id)
        writes.append((row.row_number, str(new_id)))

    if dry_run:
        return None, report

    for row_number, value in writes:
        ws.cell(row=row_number, column=ID_COLUMN_NUMBER, value=value)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue(), report
```

Two-pass ordering matters: every populated cell is added to `claimed` in the first loop before any match is assigned, so a row further down cannot be handed an id that a frozen cell above already owns.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && teststack run tests -- -k backfill -v`
Expected: PASS, all eight tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/disc_id_backfill.py backend/tests/test_disc_id_backfill.py
git commit -m "feat(import): backfill service stamping DB disc ids into the sheet"
```

---

### Task 7: Backfill CLI

**Files:**
- Create: `scripts/backfill_disc_ids.py`
- Modify: `README.md` (add the invocation to the scripts/ops section)

**Interfaces:**
- Consumes: `backfill_ids`, `BackfillReport` (Task 6).
- Produces: `uv run --project backend python scripts/backfill_disc_ids.py <xlsx_path> [--database-url URL] [--dry-run] [--output PATH]`. Exit code `0` on success, `2` on a usage error.

The database URL is supplied by the operator, so the script takes it as an argument or `$DATABASE_URL` and builds its own engine rather than importing app settings.

- [ ] **Step 1: Write the script**

There is no test harness for repo-root scripts and the logic is already covered by Task 6, so this task's verification is a real `--dry-run` against a copy of the sheet.

Create `scripts/backfill_disc_ids.py`:

```python
"""Stamp stable disc ids into the Current sheet's ID column (column K).

Usage (from repo root):
    export DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/dbname'
    uv run --project backend python scripts/backfill_disc_ids.py discs.xlsx --dry-run
    uv run --project backend python scripts/backfill_disc_ids.py discs.xlsx

Reads the database, writes only the spreadsheet. A row that resolves to an
existing disc gets that disc's real uuid; an unresolved row gets a fresh uuid.
A cell that already holds a value is never touched, so re-running is safe.

Back the file up first: openpyxl rewrites the whole workbook on save and does
not preserve charts, images, or pivot tables.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.services.disc_id_backfill import backfill_ids  # noqa: E402


def normalize_database_url(url: str) -> str:
    """asyncpg needs the +asyncpg driver marker; accept a plain psql URL too."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


async def run(*, xlsx_path: Path, output: Path, database_url: str, dry_run: bool) -> int:
    engine = create_async_engine(normalize_database_url(database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            data, report = await backfill_ids(
                xlsx_path.read_bytes(), db, dry_run=dry_run
            )
            await db.rollback()  # read-only by contract; make it explicit
    finally:
        await engine.dispose()

    print(json.dumps(report.as_dict(), indent=2))
    if dry_run:
        print("(dry-run: spreadsheet not written)")
        return 0

    output.write_bytes(data)
    print(f"wrote {output}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("xlsx_path", type=Path)
    p.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Postgres URL. Default: $DATABASE_URL.",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--output",
        type=Path,
        help="Where to write the result. Default: overwrite xlsx_path.",
    )
    args = p.parse_args()

    if not args.xlsx_path.exists():
        print(f"file not found: {args.xlsx_path}", file=sys.stderr)
        return 2
    if not args.database_url:
        print(
            "error: database URL required (set $DATABASE_URL or pass --database-url)",
            file=sys.stderr,
        )
        return 2

    return asyncio.run(
        run(
            xlsx_path=args.xlsx_path,
            output=args.output or args.xlsx_path,
            database_url=args.database_url,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the usage errors**

Run from the repo root:

```bash
uv run --project backend python scripts/backfill_disc_ids.py nope.xlsx --dry-run
```

Expected: `file not found: nope.xlsx`, exit code 2.

```bash
env -u DATABASE_URL uv run --project backend python scripts/backfill_disc_ids.py discs.xlsx --dry-run
```

Expected: `error: database URL required ...`, exit code 2.

- [ ] **Step 3: Verify a real dry run**

Ask the operator for the database URL if it is not already exported. Then:

```bash
cp discs.xlsx /tmp/discs-backup.xlsx
uv run --project backend python scripts/backfill_disc_ids.py discs.xlsx --dry-run
```

Expected: a JSON report with `already_populated`, `matched`, `generated`, `skipped`, then `(dry-run: spreadsheet not written)`. Confirm `discs.xlsx` is byte-identical: `cmp discs.xlsx /tmp/discs-backup.xlsx` prints nothing.

Do **not** run the write mode yet — that happens in Task 9 after the sheet has its `K`/`L` columns.

- [ ] **Step 4: Document the invocation**

In `README.md`, next to the existing import-script documentation, add:

```markdown
### Backfilling disc IDs

One-off: stamp stable ids into the `Current` sheet's `ID` column (K), pulling real
ids from the database where the row matches an existing disc.

```bash
cp discs.xlsx discs-backup.xlsx
export DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/dbname'
uv run --project backend python scripts/backfill_disc_ids.py discs.xlsx --dry-run
uv run --project backend python scripts/backfill_disc_ids.py discs.xlsx
```

Populated `ID` cells are never modified, so re-running is safe. `openpyxl` rewrites
the workbook on save and does not preserve charts, images, or pivot tables — keep
the backup.
```

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_disc_ids.py README.md
git commit -m "feat(scripts): CLI to backfill disc ids into the spreadsheet"
```

---

### Task 8: Preview dialog surfaces the warning and the ID

**Files:**
- Modify: `frontend/src/components/ImportPreviewDialog.tsx:18-35,61-107`
- Test: `frontend/src/components/ImportPreviewDialog.test.tsx`

**Interfaces:**
- Consumes: the plan shape from Task 4 (`created[].duplicate_warning`, `counts.possible_duplicates`).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/components/ImportPreviewDialog.test.tsx`, add `duplicate_warning: null` to every existing `created` entry and `possible_duplicates: 0` to every existing `counts` object, then append:

```tsx
test('shows the possible-duplicate count and per-row warning', () => {
  const warned: ImportPlan = {
    created: [{
      row_number: 4, manufacturer: 'Discraft', model: 'Heat', colors: ['purple'],
      owner: 'Jane Doe / +14049518881', will_notify: true, skip_reason: null,
      duplicate_warning: 'possible duplicate — new ID but matches existing disc abc-123',
    }],
    updated: [],
    unchanged: 0,
    errors: [],
    counts: { created: 1, updated: 0, unchanged: 0, errors: 0, will_notify: 1, possible_duplicates: 1 },
  }
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={warned} busy={false}
    onApprove={() => {}} onCancel={() => {}} />)
  expect(screen.getByText(/1 possible duplicate/i)).toBeInTheDocument()
  expect(screen.getByText(/matches existing disc abc-123/)).toBeInTheDocument()
})

test('hides the possible-duplicate chip when there are none', () => {
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={plan} busy={false}
    onApprove={() => {}} onCancel={() => {}} />)
  expect(screen.queryByText(/possible duplicate/i)).not.toBeInTheDocument()
})

test('error rows show the disc_id column', () => {
  const bad: ImportPlan = {
    created: [], updated: [], unchanged: 0,
    errors: [{ row: { row_number: 9, model: 'Heat', disc_id: 'not-a-uuid' }, reason: 'invalid ID' }],
    counts: { created: 0, updated: 0, unchanged: 0, errors: 1, will_notify: 0, possible_duplicates: 0 },
  }
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={bad} busy={false}
    onApprove={() => {}} onCancel={() => {}} />)
  expect(screen.getByText('disc_id')).toBeInTheDocument()
  expect(screen.getByText('not-a-uuid')).toBeInTheDocument()
  expect(screen.getByText('invalid ID')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/ImportPreviewDialog.test.tsx`
Expected: FAIL — TypeScript rejects `duplicate_warning` / `possible_duplicates` as unknown properties, and the new assertions find nothing.

- [ ] **Step 3: Write the implementation**

In `frontend/src/components/ImportPreviewDialog.tsx`, extend the types:

```tsx
export type PlannedNew = PlannedDisc & {
  will_notify: boolean
  skip_reason: string | null
  duplicate_warning: string | null
}
```

```tsx
  counts: {
    created: number
    updated: number
    unchanged: number
    errors: number
    will_notify: number
    possible_duplicates: number
  }
```

Add `disc_id` to the error table columns so a rejected ID is visible:

```tsx
const ERROR_COLS = [
  'row_number', 'first_name', 'last_name', 'phone', 'manufacturer',
  'model', 'colors', 'notes', 'input_date', 'returned', 'returned_date', 'disc_id',
]
```

Add a chip after the errors chip in the counts row:

```tsx
          {c.possible_duplicates > 0 && (
            <span className="rounded bg-destructive/10 px-2 py-1 text-destructive">
              {c.possible_duplicates} possible duplicate{c.possible_duplicates === 1 ? '' : 's'}
            </span>
          )}
```

Render the per-row warning inside the shared `line` helper so it appears in both the will-text and no-text groups:

```tsx
          const line = (d: PlannedNew) => (
            <>
              {d.manufacturer} <span>{d.model}</span> [{d.colors.join(' ')}]{d.owner ? ` — ${d.owner}` : ''}
              {d.duplicate_warning && (
                <span className="ml-1 text-destructive">⚠ {d.duplicate_warning}</span>
              )}
            </>
          )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/ImportPreviewDialog.test.tsx`
Expected: PASS, all tests including the two pre-existing ones.

Run: `cd frontend && npm run build`
Expected: `tsc -b` clean. If `AdminDiscsPage.tsx` fails to typecheck because it constructs an `ImportPlan` literal, add the two new fields there too.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ImportPreviewDialog.tsx frontend/src/components/ImportPreviewDialog.test.tsx
git commit -m "feat(import): show possible-duplicate warnings in the preview dialog"
```

---

### Task 9: Prepare the spreadsheet and run the backfill

**Files:**
- Modify: `discs.xlsx` (untracked working file — not committed)
- Modify: `README.md` (spreadsheet maintenance section)

**Interfaces:**
- Consumes: Task 7's CLI.
- Produces: a `discs.xlsx` whose `Current` sheet has frozen ids, ready for an ID-aware import.

This task is operational. Do the steps in order — the order is what prevents overwriting good ids.

- [ ] **Step 1: Back up and add the columns**

```bash
cp discs.xlsx discs-backup-$(date +%Y%m%d).xlsx
```

Open `discs.xlsx`, `Current` sheet. Set `K3` = `ID`, `L3` = `ID gen`. Leave `K4` and below empty.

Put this in `L4` and fill down past the last data row:

```
=IF($K4<>"",$K4,LOWER(DEC2HEX(RANDBETWEEN(0,4294967295),8)&"-"&DEC2HEX(RANDBETWEEN(0,65535),4)&"-4"&DEC2HEX(RANDBETWEEN(0,4095),3)&"-"&DEC2HEX(RANDBETWEEN(8,11),1)&DEC2HEX(RANDBETWEEN(0,4095),3)&"-"&DEC2HEX(RANDBETWEEN(0,65535),4)&DEC2HEX(RANDBETWEEN(0,4294967295),8)))
```

Save. Do **not** freeze yet — the backfill must see empty `K` cells so it can supply real database ids instead of freshly invented ones.

- [ ] **Step 2: Dry-run the backfill and review**

```bash
export DATABASE_URL='<url the operator provides>'
uv run --project backend python scripts/backfill_disc_ids.py discs.xlsx --dry-run
```

Read the report. `matched` should account for most rows — the `Current` sheet holds ~250 rows and they should mostly exist in the database already. A `generated` count in the same order as `matched` means the fuzzy match is failing broadly; stop and investigate rather than proceeding. Report `skipped` entries to the operator.

- [ ] **Step 3: Run the backfill for real**

```bash
uv run --project backend python scripts/backfill_disc_ids.py discs.xlsx
```

Open the file and confirm `K4` onward holds literal uuid text (formula bar shows no leading `=`).

- [ ] **Step 4: Freeze, then verify with a preview**

Freeze so `L` and `K` agree and future rows follow the documented ritual: select `L4` to the last data row, Copy, click `K4`, paste values only (Mac `Cmd+Ctrl+V` → **Values** → OK; Windows `Ctrl+Alt+V`, `V`, `Enter`; Sheets `Cmd/Ctrl+Shift+V`). Because `L` echoes a populated `K`, this cannot change any backfilled id. Save.

Then upload the sheet through the admin import preview. Expected: near-zero `new`, no `possible duplicates`, and errors only for rows that already errored before this change (missing `Date found`). A large `new` count means the backfill mismatched — do **not** approve; investigate.

- [ ] **Step 5: Document sheet maintenance and commit**

Add to `README.md`, near the import documentation:

```markdown
### Spreadsheet ID column

The `Current` sheet's column `K` (`ID`) holds a stable uuid per disc. The import
matches on it, so an edit to a disc's colors or phone updates that disc instead of
creating a duplicate. Column `L` (`ID gen`) generates ids and is ignored by the app.

`L4`, filled down:

```
=IF($K4<>"",$K4,LOWER(DEC2HEX(RANDBETWEEN(0,4294967295),8)&"-"&DEC2HEX(RANDBETWEEN(0,65535),4)&"-4"&DEC2HEX(RANDBETWEEN(0,4095),3)&"-"&DEC2HEX(RANDBETWEEN(8,11),1)&DEC2HEX(RANDBETWEEN(0,4095),3)&"-"&DEC2HEX(RANDBETWEEN(0,65535),4)&DEC2HEX(RANDBETWEEN(0,4294967295),8)))
```

**After adding rows, freeze the new ids** — a live formula recalculates and its uuid
changes, which would duplicate discs:

1. Select `L4` through the last data row, Copy.
2. Click `K4`.
3. Paste values only — Mac Excel `Cmd+Ctrl+V` → **Values** → OK; Windows Excel
   `Ctrl+Alt+V`, `V`, `Enter`; Google Sheets `Cmd/Ctrl+Shift+V`.
4. Check a `K` cell: the formula bar must show raw text, not a leading `=`.
5. Save.

Because `L` echoes a populated `K`, re-freezing the whole column never changes an
existing id. Paste `L` → `K` only, and never include rows 1–3.

The import rejects a row whose `K` holds a live formula (`ID is a live formula —
freeze with Paste Special > Values`), a malformed uuid (`invalid ID`), or an id that
appears twice (`duplicate ID in sheet`). It also flags a row whose id is unknown but
whose fields match an existing disc as a possible duplicate in the preview — that is
the signal that a freeze was missed.
```

```bash
git add README.md
git commit -m "docs: document the Current sheet ID column and freeze procedure"
```

`discs.xlsx` is untracked (it is in the working tree only) — do not add it.

---

## Notes for the implementer

- Backend tests need Postgres via teststack; there is no sqlite fallback. Run `teststack run tests` from `backend/`.
- `parse_current_sheet` now loads the workbook twice. That is deliberate: `data_only=True` returns Excel's cached value for a formula cell, so it cannot distinguish a frozen uuid from a live formula that happens to have evaluated to one.
- A file written by `openpyxl` (as the tests do) has no formula cache, so a formula cell reads as `None` in the `data_only=True` pass and as `"=..."` in the other. Both paths land on `FORMULA_ID_ERROR`, which is why the Task 2 formula test works without Excel ever touching the file.
- Nothing in this plan rewrites an existing `discs.id`, so `disc_photos` and `disc_pickup_notifications` foreign keys are never at risk.
