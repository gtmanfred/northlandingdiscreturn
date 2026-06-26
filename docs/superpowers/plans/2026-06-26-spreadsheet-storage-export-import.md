# Spreadsheet Storage, Export & Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cover all Current-sheet data in the app, add an admin XLSX export matching Roger's layout, and an admin XLSX import that upserts the Current sheet.

**Architecture:** Backend (FastAPI + async SQLAlchemy) gains a nullable owner phone, a `Disc.returned_date` column, a shared disc-filter helper, an openpyxl workbook builder, an XLSX parser, and an upsert importer. Two new admin endpoints (`GET /discs/export`, `POST /discs/import`) reuse the existing repository and owner-resolution paths. The React frontend (orval-generated client) adds download + upload controls to the admin disc list.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, openpyxl (already a dependency), pytest-asyncio, React + TypeScript, orval, axios, TanStack Query.

## Global Constraints

- Python is async throughout; repositories use `AsyncSession`, tests are `async def` using the `db` and `client` fixtures from `tests/conftest.py`.
- Phone numbers normalize via `app.phone.normalize_phone` (E.164 `+1XXXXXXXXXX`); blank → `None`.
- openpyxl pinned at `>=3.1` (already in `pyproject.toml`); no new backend deps.
- Export column order is exactly: `Name, Phone, Mfr, Model, Color, Other, Code, Date found, Date returned, Date contacted`.
- Import keys on: `input_date` + `manufacturer` + `name` + normalized `colors` + owner `phone_number`; all compared trimmed + case-insensitive; phone may be null.
- Returns are one-way on import: the sheet may set returned, never un-return an in-app disc.
- The frontend API client (`src/api/northlanding.ts`) is generated — never hand-edit it; run `npm run generate:all` after backend endpoint changes.
- Git remotes are SSH; if a push is blocked, tell the user to push manually. End commit messages with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

### Task 1: Migration — nullable phone + `returned_date`

**Files:**
- Create: `backend/alembic/versions/d3e4f5a6b7c8_nullable_phone_and_returned_date.py`
- Modify: `backend/app/models/owner.py:27` (phone_number nullable), `backend/app/models/disc.py` (add `returned_date`)
- Test: `backend/tests/test_discs.py`

**Interfaces:**
- Produces: `Owner.phone_number: Mapped[str | None]`; `Disc.returned_date: Mapped[date | None]`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_discs.py`:

```python
async def test_owner_allows_null_phone(db):
    from app.models.owner import Owner
    owner = Owner(first_name="No", last_name="Phone", phone_number=None)
    db.add(owner)
    await db.flush()
    await db.refresh(owner)
    assert owner.phone_number is None


async def test_disc_has_returned_date_default_none(db):
    repo = DiscRepository(db)
    disc = await repo.create(
        manufacturer="Innova", name="Roc", colors=["Red"], input_date=date.today()
    )
    assert disc.returned_date is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_discs.py::test_owner_allows_null_phone tests/test_discs.py::test_disc_has_returned_date_default_none -v`
Expected: FAIL — `returned_date` attribute missing / NOT NULL violation on phone.

- [ ] **Step 3: Update the models**

In `backend/app/models/owner.py`, change the `phone_number` column:

```python
    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
```

In `backend/app/models/disc.py`, add after `input_date` (line 23):

```python
    returned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
```

(`date` and `Date` are already imported in `disc.py`.)

- [ ] **Step 4: Write the migration**

Create `backend/alembic/versions/d3e4f5a6b7c8_nullable_phone_and_returned_date.py`:

```python
"""nullable owner phone and disc returned_date

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("owners", "phone_number", existing_type=sa.String(), nullable=True)
    op.add_column("discs", sa.Column("returned_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("discs", "returned_date")
    op.execute("UPDATE owners SET phone_number = '' WHERE phone_number IS NULL")
    op.alter_column("owners", "phone_number", existing_type=sa.String(), nullable=False)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_discs.py -v`
Expected: PASS (the test schema is created from the models; new tests green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/owner.py backend/app/models/disc.py backend/alembic/versions/d3e4f5a6b7c8_nullable_phone_and_returned_date.py backend/tests/test_discs.py
git commit -m "feat(discs): nullable owner phone and disc returned_date column

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Owner resolution + SMS guards for null phone

**Files:**
- Modify: `backend/app/repositories/owner.py:11-32` (`resolve_or_create` accepts null phone)
- Modify: `backend/app/services/heads_up.py:22`, `backend/app/services/welcome.py`, `backend/app/services/notification.py:~39`
- Test: `backend/tests/test_owners.py`, `backend/tests/test_discs.py`

**Interfaces:**
- Consumes: `Owner.phone_number: str | None` (Task 1).
- Produces: `OwnerRepository.resolve_or_create(*, first_name, last_name, phone_number: str | None) -> Owner`; SMS senders return `False` without enqueuing when the owner has no phone.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_owners.py`:

```python
async def test_resolve_or_create_null_phone(db):
    from app.repositories.owner import OwnerRepository
    repo = OwnerRepository(db)
    owner = await repo.resolve_or_create(first_name="No", last_name="Phone", phone_number=None)
    assert owner.id is not None
    assert owner.phone_number is None
    # second call with same null-phone identity returns the same row
    again = await repo.resolve_or_create(first_name="No", last_name="Phone", phone_number=None)
    assert again.id == owner.id
```

Add to `backend/tests/test_discs.py`:

```python
async def test_heads_up_skipped_when_no_phone(db):
    from app.models.owner import Owner
    from app.services.heads_up import maybe_enqueue_heads_up
    owner = Owner(first_name="No", last_name="Phone", phone_number=None)
    db.add(owner)
    await db.flush()
    repo = DiscRepository(db)
    disc = await repo.create(
        manufacturer="Innova", name="Wraith", colors=["Blue"],
        input_date=date.today(), owner_id=owner.id,
    )
    disc.owner = owner
    enqueued = await maybe_enqueue_heads_up(owner=owner, disc=disc, db=db)
    assert enqueued is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_owners.py::test_resolve_or_create_null_phone tests/test_discs.py::test_heads_up_skipped_when_no_phone -v`
Expected: FAIL — `resolve_or_create` query mismatches on `None`; heads-up still returns `True`.

- [ ] **Step 3: Update `resolve_or_create`**

In `backend/app/repositories/owner.py`, change the signature and lookup to handle null phone:

```python
    async def resolve_or_create(
        self, *, first_name: str, last_name: str, phone_number: str | None
    ) -> Owner:
        result = await self.db.execute(
            select(Owner).where(
                Owner.first_name == first_name,
                Owner.last_name == last_name,
                Owner.phone_number.is_(phone_number) if phone_number is None
                else Owner.phone_number == phone_number,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        owner = Owner(
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
        )
        self.db.add(owner)
        await self.db.flush()
        await self.db.refresh(owner)
        return owner
```

- [ ] **Step 4: Guard the SMS senders**

In `backend/app/services/heads_up.py`, at the top of `maybe_enqueue_heads_up`, after the `is_found` check:

```python
    if not disc.is_found:
        return False
    if not owner.phone_number:
        return False
```

In `backend/app/services/welcome.py`, in `maybe_enqueue_welcome`, after the `welcome_sent_at` check:

```python
    if owner.welcome_sent_at is not None:
        return False
    if not owner.phone_number:
        return False
```

In `backend/app/services/notification.py`, inside the `for disc in unreturned:` loop, replace the `if disc.owner is None: continue` guard with:

```python
        if disc.owner is None or not disc.owner.phone_number:
            continue
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_owners.py tests/test_discs.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories/owner.py backend/app/services/heads_up.py backend/app/services/welcome.py backend/app/services/notification.py backend/tests/test_owners.py backend/tests/test_discs.py
git commit -m "feat(owners): support null phone, skip SMS when no phone

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Stamp `returned_date` on the return transition

**Files:**
- Modify: `backend/app/routers/discs.py:101-142` (`update_disc`)
- Modify: `backend/app/schemas/disc.py` (`DiscOut` add `returned_date`)
- Test: `backend/tests/test_discs.py`

**Interfaces:**
- Consumes: `Disc.returned_date` (Task 1).
- Produces: PATCH `/discs/{id}` stamps `returned_date=date.today()` when `is_returned` goes false→true, clears it on true→false; `DiscOut.returned_date: date | None`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_discs.py`:

```python
async def test_returned_date_stamped_and_cleared(db, client):
    from app.repositories.user import UserRepository
    from app.services.auth import create_access_token
    user_repo = UserRepository(db)
    admin = await user_repo.create(email="admin@x.com", is_admin=True)
    await db.flush()
    token = create_access_token(str(admin.id))
    headers = {"Authorization": f"Bearer {token}"}

    repo = DiscRepository(db)
    disc = await repo.create(
        manufacturer="Innova", name="Teebird", colors=["White"], input_date=date.today()
    )
    await db.flush()

    r = await client.patch(f"/discs/{disc.id}", json={"is_returned": True}, headers=headers)
    assert r.status_code == 200
    assert r.json()["returned_date"] == date.today().isoformat()

    r = await client.patch(f"/discs/{disc.id}", json={"is_returned": False}, headers=headers)
    assert r.status_code == 200
    assert r.json()["returned_date"] is None
```

(Match the admin-user creation pattern already used elsewhere in `test_discs.py`; adjust the `UserRepository.create` call to the real signature if it differs.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_discs.py::test_returned_date_stamped_and_cleared -v`
Expected: FAIL — response has no `returned_date` key.

- [ ] **Step 3: Add `returned_date` to `DiscOut`**

In `backend/app/schemas/disc.py`, in `DiscOut`, after `is_returned: bool`:

```python
    returned_date: date | None = None
```

- [ ] **Step 4: Stamp/clear in `update_disc`**

In `backend/app/routers/discs.py`, after `payload = body.model_dump(exclude_unset=True)` and before `await repo.update(...)`, add:

```python
    if "is_returned" in fields_set:
        if body.is_returned and not disc.is_returned:
            payload["returned_date"] = date.today()
        elif body.is_returned is False and disc.is_returned:
            payload["returned_date"] = None
```

Add `from datetime import date` to the imports at the top of `discs.py` if not present.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_discs.py::test_returned_date_stamped_and_cleared -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/discs.py backend/app/schemas/disc.py backend/tests/test_discs.py
git commit -m "feat(discs): stamp returned_date on return transition

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Shared filter helper + export query

**Files:**
- Modify: `backend/app/repositories/disc.py` (extract filter helper, add `list_for_export` + `last_contact_dates`)
- Test: `backend/tests/test_discs.py`

**Interfaces:**
- Produces:
  - `DiscRepository.list_for_export(*, is_found, is_returned, owner_name) -> list[Disc]` — all matching discs (no pagination), owner + photos eager-loaded, same filters as `list_all`.
  - `DiscRepository.last_contact_dates(disc_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]` — latest pickup-notification `sent_at` per disc.
- Consumes: existing `list_all` filter semantics.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_discs.py`:

```python
async def test_list_for_export_ignores_pagination(db):
    repo = DiscRepository(db)
    for i in range(3):
        await repo.create(
            manufacturer="Innova", name=f"D{i}", colors=["Red"], input_date=date.today()
        )
    await db.flush()
    rows = await repo.list_for_export(is_found=None, is_returned=None, owner_name=None)
    assert len(rows) == 3


async def test_last_contact_dates(db):
    from app.models.pickup_event import PickupEvent, DiscPickupNotification
    from datetime import datetime, timezone
    repo = DiscRepository(db)
    disc = await repo.create(
        manufacturer="Innova", name="Aviar", colors=["Red"], input_date=date.today()
    )
    event = PickupEvent(
        start_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    db.add(event)
    await db.flush()
    n = DiscPickupNotification(
        disc_id=disc.id, pickup_event_id=event.id,
        sent_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    db.add(n)
    await db.flush()
    result = await repo.last_contact_dates([disc.id])
    assert result[disc.id] == datetime(2026, 6, 2, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_discs.py::test_list_for_export_ignores_pagination tests/test_discs.py::test_last_contact_dates -v`
Expected: FAIL — methods not defined.

- [ ] **Step 3: Extract the filter helper and add methods**

In `backend/app/repositories/disc.py`, add a private helper and refactor `list_all`/`count_all` to use it, then add the new methods:

```python
    @staticmethod
    def _apply_filters(stmt, *, is_found, is_returned, owner_name):
        from app.models.owner import Owner
        if owner_name is not None:
            stmt = stmt.join(Owner, Disc.owner_id == Owner.id).where(
                func.concat(Owner.first_name, " ", Owner.last_name).ilike(f"%{owner_name}%")
            )
        if is_found is not None:
            stmt = stmt.where(Disc.is_found == is_found)
        if is_returned is not None:
            stmt = stmt.where(Disc.is_returned == is_returned)
        return stmt

    async def list_for_export(
        self, *, is_found=None, is_returned=None, owner_name=None
    ) -> list[Disc]:
        stmt = (
            select(Disc)
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
            .order_by(Disc.created_at.desc())
        )
        stmt = self._apply_filters(
            stmt, is_found=is_found, is_returned=is_returned, owner_name=owner_name
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def last_contact_dates(self, disc_ids):
        from app.models.pickup_event import DiscPickupNotification
        if not disc_ids:
            return {}
        result = await self.db.execute(
            select(
                DiscPickupNotification.disc_id,
                func.max(DiscPickupNotification.sent_at),
            )
            .where(DiscPickupNotification.disc_id.in_(disc_ids))
            .group_by(DiscPickupNotification.disc_id)
        )
        return {disc_id: sent_at for disc_id, sent_at in result.all()}
```

Refactor `list_all` to call `self._apply_filters(stmt, ...)` for its three filter blocks (keep the offset/limit/order), and `count_all` likewise. Keep behavior identical.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_discs.py -v`
Expected: PASS (new tests green; existing list/count tests still green).

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/disc.py backend/tests/test_discs.py
git commit -m "feat(discs): shared filter helper, export query, contact dates

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: XLSX workbook builder

**Files:**
- Create: `backend/app/services/disc_export.py`
- Test: `backend/tests/test_disc_export.py`

**Interfaces:**
- Produces:
  - `DISC_EXPORT_COLUMNS: list[str]` — the 10 column headers in order.
  - `build_current_sheet_workbook(rows: list[dict]) -> bytes` — each row keyed by the column names (values: str, `date`, or `None`); returns `.xlsx` bytes with a title row, a header row, then data rows. `date` values become real Excel date cells; `None` → blank.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_disc_export.py`:

```python
import io
from datetime import date
import openpyxl
from app.services.disc_export import build_current_sheet_workbook, DISC_EXPORT_COLUMNS


def test_columns_order():
    assert DISC_EXPORT_COLUMNS == [
        "Name", "Phone", "Mfr", "Model", "Color", "Other",
        "Code", "Date found", "Date returned", "Date contacted",
    ]


def test_build_workbook_roundtrip():
    rows = [{
        "Name": "Jane Doe", "Phone": "+15551234567", "Mfr": "Innova",
        "Model": "Teebird", "Color": "white", "Other": "no prev",
        "Code": "", "Date found": date(2026, 6, 1),
        "Date returned": None, "Date contacted": date(2026, 6, 3),
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_disc_export.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the builder**

Create `backend/app/services/disc_export.py`:

```python
import io
from openpyxl import Workbook

DISC_EXPORT_COLUMNS = [
    "Name", "Phone", "Mfr", "Model", "Color", "Other",
    "Code", "Date found", "Date returned", "Date contacted",
]

TITLE = "North Landing Discs Database"


def build_current_sheet_workbook(rows: list[dict]) -> bytes:
    """Build an .xlsx mirroring the Current sheet layout. Returns the file bytes."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Current"
    ws.append([TITLE])
    ws.append(DISC_EXPORT_COLUMNS)
    for row in rows:
        ws.append([row.get(col) for col in DISC_EXPORT_COLUMNS])
    for col_idx, name in enumerate(DISC_EXPORT_COLUMNS, start=1):
        if name in ("Date found", "Date returned", "Date contacted"):
            for cell in ws.iter_cols(
                min_col=col_idx, max_col=col_idx, min_row=3
            ).__next__():
                if cell.value is not None:
                    cell.number_format = "yyyy-mm-dd"
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_disc_export.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/disc_export.py backend/tests/test_disc_export.py
git commit -m "feat(discs): xlsx workbook builder for current-sheet export

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Export endpoint `GET /discs/export`

**Files:**
- Modify: `backend/app/routers/discs.py` (add endpoint)
- Test: `backend/tests/test_discs.py`

**Interfaces:**
- Consumes: `DiscRepository.list_for_export`, `last_contact_dates` (Task 4); `build_current_sheet_workbook`, `DISC_EXPORT_COLUMNS` (Task 5).
- Produces: `GET /discs/export?is_found&is_returned&owner_name` (admin-only) → streaming `.xlsx` attachment.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_discs.py`:

```python
async def test_export_xlsx_admin_only(db, client):
    from app.repositories.user import UserRepository
    from app.repositories.owner import OwnerRepository
    from app.services.auth import create_access_token
    user_repo = UserRepository(db)
    admin = await user_repo.create(email="exp@x.com", is_admin=True)
    await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(admin.id))}"}

    owner = await OwnerRepository(db).resolve_or_create(
        first_name="Jane", last_name="Doe", phone_number="+15551234567"
    )
    await db.flush()
    repo = DiscRepository(db)
    await repo.create(
        manufacturer="Innova", name="Teebird", colors=["white"],
        input_date=date(2026, 6, 1), owner_id=owner.id, notes="no prev",
    )
    await db.flush()

    r = await client.get("/discs/export", headers=headers)
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]

    import io, openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    grid = list(wb.active.iter_rows(values_only=True))
    header = grid[1]
    body = dict(zip(header, grid[2]))
    assert body["Mfr"] == "Innova"
    assert body["Name"] == "Jane Doe"
    assert body["Color"] == "white"
    assert body["Other"] == "no prev"


async def test_export_forbidden_for_non_admin(db, client):
    from app.repositories.user import UserRepository
    from app.services.auth import create_access_token
    user = await UserRepository(db).create(email="plain@x.com", is_admin=False)
    await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
    r = await client.get("/discs/export", headers=headers)
    assert r.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_discs.py::test_export_xlsx_admin_only tests/test_discs.py::test_export_forbidden_for_non_admin -v`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Implement the endpoint**

In `backend/app/routers/discs.py`, add imports near the top:

```python
from fastapi.responses import StreamingResponse
from app.services.disc_export import build_current_sheet_workbook, DISC_EXPORT_COLUMNS
```

Add the route (place it before `@router.patch("/{disc_id}")` so `/export` is not captured by `/{disc_id}`):

```python
@router.get("/export", operation_id="exportDiscs")
async def export_discs(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    is_found: bool | None = Query(default=None),
    is_returned: bool | None = Query(default=None),
    owner_name: str | None = Query(default=None),
):
    repo = DiscRepository(db)
    discs = await repo.list_for_export(
        is_found=is_found, is_returned=is_returned, owner_name=owner_name
    )
    contact = await repo.last_contact_dates([d.id for d in discs])

    rows = []
    for d in discs:
        owner = d.owner
        contacted = None
        candidates = []
        if owner and owner.heads_up_sent_at:
            candidates.append(owner.heads_up_sent_at)
        if d.id in contact and contact[d.id]:
            candidates.append(contact[d.id])
        if candidates:
            contacted = max(candidates).date()
        rows.append({
            "Name": owner.name if owner else "?",
            "Phone": owner.phone_number if owner and owner.phone_number else "",
            "Mfr": d.manufacturer,
            "Model": d.name,
            "Color": " ".join(d.colors),
            "Other": d.notes or "",
            "Code": "R" if d.is_returned else "",
            "Date found": d.input_date,
            "Date returned": d.returned_date,
            "Date contacted": contacted,
        })

    data = build_current_sheet_workbook(rows)
    today = date.today().isoformat()
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="north-landing-discs-{today}.xlsx"'
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_discs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/discs.py backend/tests/test_discs.py
git commit -m "feat(discs): GET /discs/export streams current-sheet xlsx

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: XLSX parser for the Current sheet

**Files:**
- Create: `backend/app/services/disc_import.py`
- Test: `backend/tests/test_disc_import.py`

**Interfaces:**
- Produces:
  - `@dataclass ParsedDiscRow` with fields: `row_number: int`, `first_name: str`, `last_name: str`, `phone: str | None`, `manufacturer: str`, `model: str`, `colors: list[str]`, `notes: str | None`, `input_date: date | None`, `returned: bool`, `returned_date: date | None`, `error: str | None`.
  - `parse_current_sheet(file_bytes: bytes) -> list[ParsedDiscRow]` — reads the worksheet titled `Current`; raises `ValueError("Current sheet not found")` if absent. Rows with no usable disc data (blank Mfr+Model) are skipped; a row missing a parseable `Date found` gets `error` set (and is still returned so the importer can report it).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_disc_import.py`:

```python
import io
from datetime import date
import openpyxl
import pytest
from app.services.disc_import import parse_current_sheet, ParsedDiscRow


def _make_sheet(data_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Current"
    ws.append(["North Landing Discs Database"])
    ws.append(["Sorted by ...", None, None, None, None, None, "Code: ..."])
    ws.append(["Name", "Phone", "Mfr", "Model", "Color", "Other",
               "Code", "Date found", "Date retuned", "Date contacted"])
    for r in data_rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_basic_row():
    data = _make_sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple trans",
         "Ed no prev", None, date(2026, 6, 6), None, None],
    ])
    rows = parse_current_sheet(data)
    assert len(rows) == 1
    row = rows[0]
    assert row.first_name == "Jane"
    assert row.last_name == "Doe"
    assert row.phone == "+14049518881"
    assert row.manufacturer == "Discraft"
    assert row.model == "Heat"
    assert row.colors == ["purple", "trans"]
    assert row.notes == "Ed no prev"
    assert row.input_date == date(2026, 6, 6)
    assert row.returned is False
    assert row.error is None


def test_parse_returned_row_from_date():
    data = _make_sheet([
        ["?", None, "Innova", "Roc", "blue", "donate", None,
         date(2026, 1, 1), date(2026, 2, 1), None],
    ])
    row = parse_current_sheet(data)[0]
    assert row.first_name == ""
    assert row.last_name == ""
    assert row.phone is None
    assert row.returned is True
    assert row.returned_date == date(2026, 2, 1)


def test_parse_returned_row_from_code():
    data = _make_sheet([
        ["Sam", "404-353-5987", "Axiom", "Fireball", "pink", "x", "R",
         date(2026, 1, 1), None, None],
    ])
    row = parse_current_sheet(data)[0]
    assert row.returned is True
    assert row.returned_date == date(2026, 1, 1)  # falls back to date found


def test_missing_date_found_sets_error():
    data = _make_sheet([
        ["Sam", "404-353-5987", "Axiom", "Fireball", "pink", "x", None, None, None, None],
    ])
    row = parse_current_sheet(data)[0]
    assert row.error is not None


def test_missing_current_sheet_raises():
    wb = openpyxl.Workbook()
    wb.active.title = "Other"
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError):
        parse_current_sheet(buf.getvalue())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_disc_import.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the parser**

Create `backend/app/services/disc_import.py`:

```python
import io
from dataclasses import dataclass
from datetime import date, datetime
import openpyxl
from app.phone import normalize_phone

SHEET_NAME = "Current"
HEADER_KEYWORD = "Name"


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
    error: str | None = None


def _split_name(raw) -> tuple[str, str]:
    text = (str(raw).strip() if raw is not None else "")
    if text in ("", "?"):
        return "", ""
    parts = text.split()
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], " ".join(parts[1:])


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def parse_current_sheet(file_bytes: bytes) -> list[ParsedDiscRow]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    if SHEET_NAME not in wb.sheetnames:
        raise ValueError("Current sheet not found")
    ws = wb[SHEET_NAME]
    grid = list(ws.iter_rows(values_only=True))

    header_idx = next(
        (i for i, r in enumerate(grid)
         if r and r[0] and HEADER_KEYWORD in str(r[0])),
        None,
    )
    if header_idx is None:
        raise ValueError("Header row not found in Current sheet")

    rows: list[ParsedDiscRow] = []
    for offset, r in enumerate(grid[header_idx + 1:], start=header_idx + 2):
        cells = list(r) + [None] * (10 - len(r))
        name, phone, mfr, model, color, other, code, found, returned_dt, _ = cells[:10]

        mfr = (str(mfr).strip() if mfr else "")
        model = (str(model).strip() if model else "")
        if not mfr and not model:
            continue  # blank row

        first, last = _split_name(name)
        phone_norm = None
        if phone:
            try:
                phone_norm = normalize_phone(str(phone))
            except ValueError:
                phone_norm = None

        colors = [c.lower() for c in str(color).split()] if color else []
        input_date = _as_date(found)
        ret_date = _as_date(returned_dt)
        code_str = (str(code).strip().upper() if code else "")
        returned = ret_date is not None or "R" in code_str
        if returned and ret_date is None:
            ret_date = input_date

        error = None
        if input_date is None:
            error = "missing or invalid Date found"

        rows.append(ParsedDiscRow(
            row_number=offset,
            first_name=first,
            last_name=last,
            phone=phone_norm,
            manufacturer=mfr,
            model=model,
            colors=colors,
            notes=(str(other).strip() if other else None),
            input_date=input_date,
            returned=returned,
            returned_date=ret_date if returned else None,
            error=error,
        ))
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_disc_import.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/disc_import.py backend/tests/test_disc_import.py
git commit -m "feat(discs): parse current-sheet xlsx into rows

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Upsert lookup + import service

**Files:**
- Modify: `backend/app/repositories/disc.py` (add `find_by_import_key`)
- Modify: `backend/app/services/disc_import.py` (add `import_rows` + `ImportSummary`)
- Test: `backend/tests/test_disc_import.py`

**Interfaces:**
- Consumes: `ParsedDiscRow` (Task 7); `OwnerRepository.resolve_or_create` (Task 2); `Disc.returned_date` (Task 1).
- Produces:
  - `DiscRepository.find_by_import_key(*, input_date, manufacturer, name, colors, phone) -> Disc | None`.
  - `@dataclass ImportSummary` with `created: int`, `updated: int`, `skipped: int`, `errors: list[dict]`.
  - `async import_rows(rows: list[ParsedDiscRow], db: AsyncSession) -> ImportSummary`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_disc_import.py`:

```python
import pytest
from datetime import date as _date
from app.services.disc_import import import_rows, ParsedDiscRow, ImportSummary
from app.repositories.disc import DiscRepository


def _row(**kw):
    base = dict(
        row_number=4, first_name="Jane", last_name="Doe", phone="+15551234567",
        manufacturer="Innova", model="Teebird", colors=["white"], notes="x",
        input_date=_date(2026, 6, 1), returned=False, returned_date=None, error=None,
    )
    base.update(kw)
    return ParsedDiscRow(**base)


@pytest.mark.asyncio
async def test_import_creates_then_updates(db):
    s1 = await import_rows([_row()], db)
    assert s1.created == 1 and s1.updated == 0

    # same key, changed notes -> update, not create
    s2 = await import_rows([_row(notes="changed")], db)
    assert s2.created == 0 and s2.updated == 1

    repo = DiscRepository(db)
    rows = await repo.list_for_export()
    assert len(rows) == 1
    assert rows[0].notes == "changed"


@pytest.mark.asyncio
async def test_import_returned_is_one_way(db):
    await import_rows([_row()], db)
    repo = DiscRepository(db)
    disc = (await repo.list_for_export())[0]
    # mark returned in-app
    await repo.update(disc, is_returned=True, returned_date=_date(2026, 6, 5))
    await db.flush()
    # re-import the row still showing active -> must NOT un-return
    await import_rows([_row()], db)
    disc = (await repo.list_for_export())[0]
    assert disc.is_returned is True


@pytest.mark.asyncio
async def test_import_marks_returned_from_sheet(db):
    await import_rows([_row()], db)
    await import_rows([_row(returned=True, returned_date=_date(2026, 6, 9))], db)
    repo = DiscRepository(db)
    disc = (await repo.list_for_export())[0]
    assert disc.is_returned is True
    assert disc.returned_date == _date(2026, 6, 9)


@pytest.mark.asyncio
async def test_import_reports_row_errors(db):
    summary = await import_rows([_row(error="missing or invalid Date found")], db)
    assert summary.created == 0
    assert len(summary.errors) == 1
    assert summary.errors[0]["row"] == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_disc_import.py -v`
Expected: FAIL — `import_rows` / `find_by_import_key` not defined.

- [ ] **Step 3: Add `find_by_import_key` to the repository**

In `backend/app/repositories/disc.py`:

```python
    async def find_by_import_key(
        self, *, input_date, manufacturer, name, colors, phone
    ) -> Disc | None:
        stmt = (
            select(Disc)
            .options(selectinload(Disc.owner), selectinload(Disc.photos))
            .where(Disc.input_date == input_date)
        )
        result = await self.db.execute(stmt)
        target_mfr = manufacturer.strip().lower()
        target_model = name.strip().lower()
        target_colors = [c.strip().lower() for c in colors]
        for disc in result.scalars().all():
            if disc.manufacturer.strip().lower() != target_mfr:
                continue
            if disc.name.strip().lower() != target_model:
                continue
            if [c.strip().lower() for c in disc.colors] != target_colors:
                continue
            disc_phone = disc.owner.phone_number if disc.owner else None
            if disc_phone != phone:
                continue
            return disc
        return None
```

- [ ] **Step 4: Implement the import service**

Append to `backend/app/services/disc_import.py`:

```python
from dataclasses import field
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.disc import DiscRepository
from app.repositories.owner import OwnerRepository


@dataclass
class ImportSummary:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)


async def import_rows(rows: list[ParsedDiscRow], db: AsyncSession) -> ImportSummary:
    summary = ImportSummary()
    disc_repo = DiscRepository(db)
    owner_repo = OwnerRepository(db)

    for row in rows:
        if row.error or row.input_date is None:
            summary.errors.append({"row": row.row_number, "reason": row.error or "no date found"})
            continue

        owner_id = None
        if row.phone or row.first_name or row.last_name:
            owner = await owner_repo.resolve_or_create(
                first_name=row.first_name,
                last_name=row.last_name,
                phone_number=row.phone,
            )
            owner_id = owner.id

        existing = await disc_repo.find_by_import_key(
            input_date=row.input_date,
            manufacturer=row.manufacturer,
            name=row.model,
            colors=row.colors,
            phone=row.phone,
        )

        if existing is None:
            disc = await disc_repo.create(
                manufacturer=row.manufacturer,
                name=row.model,
                colors=row.colors,
                input_date=row.input_date,
                owner_id=owner_id,
                notes=row.notes,
            )
            if row.returned:
                await disc_repo.update(
                    disc, is_returned=True, returned_date=row.returned_date
                )
            summary.created += 1
        else:
            updates = {}
            if (existing.notes or None) != (row.notes or None):
                updates["notes"] = row.notes
            if [c.strip().lower() for c in existing.colors] != [c.strip().lower() for c in row.colors]:
                updates["colors"] = row.colors
            if existing.owner_id != owner_id:
                updates["owner_id"] = owner_id
            # one-way return: only ever set returned, never clear
            if row.returned and not existing.is_returned:
                updates["is_returned"] = True
                updates["returned_date"] = row.returned_date
            if updates:
                await disc_repo.update(existing, **updates)
                summary.updated += 1
            else:
                summary.skipped += 1

    await db.flush()
    return summary
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_disc_import.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories/disc.py backend/app/services/disc_import.py backend/tests/test_disc_import.py
git commit -m "feat(discs): upsert importer with one-way returns

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Import endpoint `POST /discs/import`

**Files:**
- Modify: `backend/app/routers/discs.py` (add endpoint)
- Test: `backend/tests/test_discs.py`

**Interfaces:**
- Consumes: `parse_current_sheet`, `import_rows`, `ImportSummary` (Tasks 7-8).
- Produces: `POST /discs/import` (admin-only, multipart `file`) → `{created, updated, skipped, errors}`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_discs.py`:

```python
async def test_import_endpoint(db, client):
    import io, openpyxl
    from datetime import date as _date
    from app.repositories.user import UserRepository
    from app.services.auth import create_access_token

    admin = await UserRepository(db).create(email="imp@x.com", is_admin=True)
    await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(admin.id))}"}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Current"
    ws.append(["North Landing Discs Database"])
    ws.append(["sorted"])
    ws.append(["Name", "Phone", "Mfr", "Model", "Color", "Other",
               "Code", "Date found", "Date retuned", "Date contacted"])
    ws.append(["Jane Doe", "404-951-8881", "Innova", "Teebird", "white",
               "x", None, _date(2026, 6, 1), None, None])
    buf = io.BytesIO()
    wb.save(buf)

    files = {"file": ("sheet.xlsx", buf.getvalue(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = await client.post("/discs/import", files=files, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1
    assert body["updated"] == 0


async def test_import_rejects_missing_current_sheet(db, client):
    import io, openpyxl
    from app.repositories.user import UserRepository
    from app.services.auth import create_access_token
    admin = await UserRepository(db).create(email="imp2@x.com", is_admin=True)
    await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(admin.id))}"}
    wb = openpyxl.Workbook()
    wb.active.title = "Other"
    buf = io.BytesIO()
    wb.save(buf)
    files = {"file": ("sheet.xlsx", buf.getvalue(), "application/octet-stream")}
    r = await client.post("/discs/import", files=files, headers=headers)
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_discs.py::test_import_endpoint tests/test_discs.py::test_import_rejects_missing_current_sheet -v`
Expected: FAIL — route missing (404).

- [ ] **Step 3: Implement the endpoint**

In `backend/app/routers/discs.py`, add imports:

```python
from app.services.disc_import import parse_current_sheet, import_rows
```

(`UploadFile`, `File` are already imported.) Add the route near the export route, before `/{disc_id}`:

```python
@router.post("/import", operation_id="importDiscs")
async def import_discs(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    content = await file.read()
    try:
        rows = parse_current_sheet(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    summary = await import_rows(rows, db)
    await db.commit()
    return {
        "created": summary.created,
        "updated": summary.updated,
        "skipped": summary.skipped,
        "errors": summary.errors,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_discs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/discs.py backend/tests/test_discs.py
git commit -m "feat(discs): POST /discs/import endpoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Regenerate API client + frontend export button

**Files:**
- Modify: `frontend/src/api/northlanding.ts` (regenerated — do not hand-edit)
- Modify: `frontend/src/pages/AdminDiscsPage.tsx`
- Modify (if a helper file is preferred): `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: `GET /discs/export` (Task 6).
- Produces: a "Download spreadsheet" button on the admin disc list that downloads the filtered `.xlsx`.

- [ ] **Step 1: Regenerate the schema + client**

Run: `cd backend && uv run python ../scripts/generate-openapi.py` then `cd ../frontend && npm run generate`
(or `cd frontend && npm run generate:all`)
Expected: `northlanding.ts` updated with `exportDiscs` / `importDiscs` operations; no manual edits.

- [ ] **Step 2: Add a download handler in `AdminDiscsPage.tsx`**

Use the shared axios instance to fetch the file as a blob with the active filters, then trigger a browser download. Near the other handlers in `AdminDiscsPage.tsx`:

```tsx
import { axiosInstance } from '@/api/client'

async function handleDownloadSpreadsheet() {
  const res = await axiosInstance.get('/discs/export', {
    params: {
      is_found: isFoundFilter,
      is_returned: isReturnedFilter,
      owner_name: ownerNameFilter,
    },
    responseType: 'blob',
  })
  const url = window.URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `north-landing-discs-${new Date().toISOString().slice(0, 10)}.xlsx`
  a.click()
  window.URL.revokeObjectURL(url)
}
```

- [ ] **Step 3: Add the button to the toolbar**

Next to the existing "Add disc" `Button` (around line 127):

```tsx
<Button variant="outline" onClick={handleDownloadSpreadsheet}>
  Download spreadsheet
</Button>
```

- [ ] **Step 4: Verify the build**

Run: `cd frontend && npm run build`
Expected: build succeeds (TypeScript clean).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/northlanding.ts frontend/src/pages/AdminDiscsPage.tsx backend/openapi.json
git commit -m "feat(frontend): download discs spreadsheet from admin list

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

(Include whatever schema artifact `generate-openapi.py` writes; check `git status` for its path.)

---

### Task 11: Frontend import control

**Files:**
- Modify: `frontend/src/pages/AdminDiscsPage.tsx`

**Interfaces:**
- Consumes: `POST /discs/import` (Task 9); `useListDiscs` query key for refetch.
- Produces: an "Import spreadsheet" file picker that uploads the `.xlsx` and shows the summary.

- [ ] **Step 1: Add an import handler**

In `AdminDiscsPage.tsx`, add state and a handler. Use `useQueryClient` to invalidate the disc list after a successful import:

```tsx
import { useQueryClient } from '@tanstack/react-query'
import { getListDiscsQueryKey } from '@/api/northlanding'

const queryClient = useQueryClient()
const [importMsg, setImportMsg] = useState('')

async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
  const file = e.target.files?.[0]
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await axiosInstance.post('/discs/import', form)
    const s = res.data as { created: number; updated: number; skipped: number; errors: unknown[] }
    setImportMsg(`Imported: ${s.created} new, ${s.updated} updated, ${s.skipped} unchanged, ${s.errors.length} errors`)
    await queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
  } catch {
    setImportMsg('Import failed. Check the file and try again.')
  } finally {
    e.target.value = ''
  }
}
```

- [ ] **Step 2: Add the import control to the toolbar**

Next to the download button:

```tsx
<Button variant="outline" asChild>
  <label>
    Import spreadsheet
    <input type="file" accept=".xlsx" className="hidden" onChange={handleImportFile} />
  </label>
</Button>
{importMsg && <p className="text-sm text-muted-foreground">{importMsg}</p>}
```

- [ ] **Step 3: Verify the build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Manual smoke check (optional but recommended)**

Start the stack, open the admin disc list, upload the real Current sheet, confirm the summary message and that the list refreshes.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AdminDiscsPage.tsx
git commit -m "feat(frontend): import discs spreadsheet from admin list

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for the implementer

- `UserRepository.create(...)` signature in the test stubs is illustrative — match the real one used elsewhere in `tests/test_discs.py` / `tests/test_admin.py` (those files already create admin users; copy their exact pattern).
- Route ordering matters: `/discs/export` and `/discs/import` must be declared before `/discs/{disc_id}` or FastAPI will treat `export`/`import` as a `disc_id` path param.
- The frontend client is generated; if `npm run generate` does not produce typed blob/upload helpers you like, calling `axiosInstance` directly (as the plan does) is the intended approach for binary download + multipart upload.
