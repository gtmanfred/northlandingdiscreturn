# Import Preview & Approve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin preview what a spreadsheet import would do (new / updated / unchanged counts, browsable disc lists with field diffs, and full error-row contents) and explicitly approve before any database write or SMS is sent.

**Architecture:** Split import into a read-only `plan_import` phase and the existing write phase (renamed `apply_import`). A new `import_staging` table holds the parsed rows (JSONB) plus the computed plan between preview and approval. Three endpoints replace the one-shot `POST /discs/import`: `preview`, `{id}/apply`, `{id}/cancel`. The admin UI opens a preview dialog and calls apply/cancel.

**Tech Stack:** FastAPI, SQLAlchemy (async) + PostgreSQL JSONB, Alembic, openpyxl; React + TypeScript, TanStack Query, Vitest + Testing Library, axios.

## Global Constraints

- Backend tests run in the teststack container against real PostgreSQL (JSONB, ARRAY, enums are used). Local edits are NOT live-mounted — copy them in first, then run:
  ```
  cd backend && docker cp app backend_tests:/srv/ && docker cp tests backend_tests:/srv/ && docker cp alembic backend_tests:/srv/ && teststack run -s tests -- tests/<file>.py -v
  ```
  (Do NOT `docker cp .` — it would clobber the container's Linux `.venv` with the local macOS one.)
- `asyncio_mode = "auto"` — async test functions need no `@pytest.mark.asyncio` decorator (existing tests omit it).
- Alembic current head is `e4f5a6b7c8d9`. New migration's `down_revision` MUST be `e4f5a6b7c8d9`.
- New migration revision format follows `e4f5a6b7c8d9_...py` (`revision: str = '...'`, `down_revision: Union[str, Sequence[str], None] = '...'`).
- Every new SQLAlchemy model MUST be imported in `backend/app/models/__init__.py` so `Base.metadata.create_all` (used by the test `engine` fixture) creates its table.
- Apply-phase behavior (disc matching, create/update rules, one-way return, welcome + heads-up SMS enqueue) MUST remain byte-for-byte identical to today's `import_rows`.
- Admin endpoints authenticate via `Authorization: Bearer <create_access_token(str(user_id))>` for an `is_admin=True` user (see `admin_headers` / `make_admin` in `tests/test_discs.py`).
- Frontend tests run with `cd frontend && npx vitest run <path>`.

---

### Task 1: Extract shared update-detection helper and rename `import_rows` → `apply_import`

Behavior-preserving refactor. Pull the "what fields change on an existing disc" logic into one helper, and rename the write entry point. No functional change.

**Files:**
- Modify: `backend/app/services/disc_import.py` (the `import_rows` function, lines ~120-185)
- Modify: `backend/tests/test_disc_import.py` (imports + call sites use `apply_import`)

**Interfaces:**
- Produces: `_compute_updates(existing: Disc, row: ParsedDiscRow, owner_id: uuid.UUID | None) -> dict` — the updates dict for an existing disc.
- Produces: `apply_import(rows: list[ParsedDiscRow], db: AsyncSession) -> ImportSummary` (renamed from `import_rows`, identical behavior).

- [ ] **Step 1: Update existing tests to the new name (make them the failing spec)**

In `backend/tests/test_disc_import.py`, change the import line and every call:

```python
from app.services.disc_import import parse_current_sheet, ParsedDiscRow, apply_import, ImportSummary
```

Then replace every `import_rows(` with `apply_import(` in that file (10 call sites: the `s1 = await import_rows(...)` etc. throughout).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_disc_import.py -v`
Expected: FAIL with `ImportError: cannot import name 'apply_import'`.

- [ ] **Step 3: Add the helper and rename the function**

In `backend/app/services/disc_import.py`, add this helper just above the `ImportSummary` dataclass (after `parse_current_sheet`):

```python
def _compute_updates(existing, row: "ParsedDiscRow", owner_id) -> dict:
    """Fields that would change on an existing disc for this row. Empty dict = unchanged."""
    updates: dict = {}
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
    return updates
```

Rename `async def import_rows(` to `async def apply_import(`. Replace the inline updates-building block in the `else` branch (currently lines ~167-177) with a call to the helper:

```python
        else:
            updates = _compute_updates(existing, row, owner_id)
            if updates:
                await disc_repo.update(existing, **updates)
                summary.updated += 1
            else:
                summary.skipped += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_disc_import.py -v`
Expected: PASS (all existing tests green).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/disc_import.py backend/tests/test_disc_import.py
git commit -m "refactor(import): extract _compute_updates, rename import_rows to apply_import"
```

---

### Task 2: Read-only `plan_import` with serializable `ImportPlan`

Add the read-only classification phase plus JSON (de)serialization for staging.

**Files:**
- Modify: `backend/app/services/disc_import.py`
- Test: `backend/tests/test_disc_plan.py` (create)

**Interfaces:**
- Consumes: `parse_current_sheet`, `ParsedDiscRow`, `DiscRepository.find_by_import_key`.
- Produces: `row_to_dict(r: ParsedDiscRow) -> dict` and `row_from_dict(d: dict) -> ParsedDiscRow` (round-trip; dates as ISO strings).
- Produces: `ImportPlan` dataclass with `created: list[dict]`, `updated: list[dict]`, `unchanged: int`, `errors: list[dict]`, and `to_dict() -> dict`.
- Produces: `async def plan_import(rows: list[ParsedDiscRow], db: AsyncSession) -> ImportPlan` — performs NO writes and enqueues NO SMS.
- Plan dict shapes: created/updated items `{row_number, manufacturer, model, colors, owner}`; updated items also carry `diffs: list[{field, old, new}]`; errors items `{row: <row_to_dict>, reason}`; `to_dict()` adds `counts: {created, updated, unchanged, errors}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_disc_plan.py`:

```python
from datetime import date as _date
from sqlalchemy import select
from app.services.disc_import import (
    ParsedDiscRow, plan_import, apply_import, row_to_dict, row_from_dict,
)
from app.repositories.disc import DiscRepository
from app.models.disc import Disc
from app.models.pickup_event import SMSJob


def _row(**kw):
    base = dict(
        row_number=4, first_name="Jane", last_name="Doe", phone="+15551234567",
        manufacturer="Innova", model="Teebird", colors=["white"], notes="x",
        input_date=_date(2026, 6, 1), returned=False, returned_date=None, error=None,
    )
    base.update(kw)
    return ParsedDiscRow(**base)


def test_row_dict_round_trip():
    r = _row(returned=True, returned_date=_date(2026, 6, 5))
    r2 = row_from_dict(row_to_dict(r))
    assert r2 == r


async def test_plan_classifies_created(db):
    plan = await plan_import([_row()], db)
    d = plan.to_dict()
    assert d["counts"]["created"] == 1
    assert d["counts"]["updated"] == 0
    assert d["created"][0]["model"] == "Teebird"
    assert d["created"][0]["owner"] is not None


async def test_plan_makes_no_writes_and_no_sms(db):
    await plan_import([_row()], db)
    discs = (await db.execute(select(Disc))).scalars().all()
    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert len(discs) == 0
    assert len(jobs) == 0


async def test_plan_classifies_updated_with_diffs(db):
    await apply_import([_row()], db)
    plan = await plan_import([_row(notes="changed")], db)
    d = plan.to_dict()
    assert d["counts"]["updated"] == 1
    diff = d["updated"][0]["diffs"]
    assert {"field": "notes", "old": "x", "new": "changed"} in diff


async def test_plan_classifies_unchanged(db):
    await apply_import([_row()], db)
    plan = await plan_import([_row()], db)
    assert plan.to_dict()["counts"]["unchanged"] == 1


async def test_plan_captures_error_rows_full_content(db):
    plan = await plan_import([_row(error="missing or invalid Date found", input_date=None)], db)
    d = plan.to_dict()
    assert d["counts"]["errors"] == 1
    err = d["errors"][0]
    assert err["reason"] == "missing or invalid Date found"
    assert err["row"]["manufacturer"] == "Innova"
    assert err["row"]["model"] == "Teebird"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_disc_plan.py -v`
Expected: FAIL with `ImportError: cannot import name 'plan_import'`.

- [ ] **Step 3: Implement plan phase and serialization**

Append to `backend/app/services/disc_import.py` (after `apply_import`):

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
        "error": r.error,
    }


def row_from_dict(d: dict) -> ParsedDiscRow:
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
        error=d["error"],
    )


def _owner_label_from_row(row: ParsedDiscRow) -> str | None:
    name = f"{row.first_name} {row.last_name}".strip()
    parts = [p for p in (name, row.phone) if p]
    return " / ".join(parts) if parts else None


def _owner_label(owner) -> str | None:
    if owner is None:
        return None
    name = f"{owner.first_name} {owner.last_name}".strip()
    parts = [p for p in (name, owner.phone_number) if p]
    return " / ".join(parts) if parts else None


def _disc_label(row: ParsedDiscRow) -> dict:
    return {
        "manufacturer": row.manufacturer,
        "model": row.model,
        "colors": row.colors,
        "owner": _owner_label_from_row(row),
    }


def _plan_diffs(existing, row: ParsedDiscRow) -> list[dict]:
    """Human-readable field changes for display. Semantic (does not use owner_id)."""
    diffs: list[dict] = []
    if (existing.notes or None) != (row.notes or None):
        diffs.append({"field": "notes", "old": existing.notes, "new": row.notes})
    if [c.strip().lower() for c in existing.colors] != [c.strip().lower() for c in row.colors]:
        diffs.append({"field": "colors", "old": existing.colors, "new": row.colors})
    row_has_owner = bool(row.phone or row.first_name or row.last_name)
    old_owner = _owner_label(existing.owner)
    new_owner = _owner_label_from_row(row)
    if row_has_owner and old_owner != new_owner:
        diffs.append({"field": "owner", "old": old_owner, "new": new_owner})
    if row.returned and not existing.is_returned:
        diffs.append({"field": "returned", "old": False, "new": True})
    return diffs


@dataclass
class ImportPlan:
    created: list[dict] = field(default_factory=list)
    updated: list[dict] = field(default_factory=list)
    unchanged: int = 0
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "errors": self.errors,
            "counts": {
                "created": len(self.created),
                "updated": len(self.updated),
                "unchanged": self.unchanged,
                "errors": len(self.errors),
            },
        }


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
        existing = await disc_repo.find_by_import_key(
            input_date=row.input_date,
            manufacturer=row.manufacturer,
            name=row.model,
            colors=row.colors,
            phone=row.phone,
        )
        label = {"row_number": row.row_number, **_disc_label(row)}
        if existing is None:
            plan.created.append(label)
        else:
            diffs = _plan_diffs(existing, row)
            if diffs:
                plan.updated.append({**label, "diffs": diffs})
            else:
                plan.unchanged += 1
    return plan
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_disc_plan.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/disc_import.py backend/tests/test_disc_plan.py
git commit -m "feat(import): add read-only plan_import with serializable ImportPlan"
```

---

### Task 3: `ImportStaging` model + Alembic migration

**Files:**
- Create: `backend/app/models/import_staging.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/f5a6b7c8d9e0_add_import_staging.py`
- Test: `backend/tests/test_import_staging_model.py` (create)

**Interfaces:**
- Produces: `ImportStaging` with columns `id: uuid`, `created_at: datetime`, `created_by: uuid`, `filename: str | None`, `status: str`, `rows: list`, `plan: dict`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_import_staging_model.py`:

```python
import uuid
from sqlalchemy import select
from app.models.import_staging import ImportStaging


async def test_import_staging_persists_jsonb(db):
    row = ImportStaging(
        created_by=uuid.uuid4(),
        filename="discs.xlsx",
        status="pending",
        rows=[{"row_number": 4, "model": "Teebird"}],
        plan={"counts": {"created": 1}},
    )
    db.add(row)
    await db.flush()
    fetched = (await db.execute(select(ImportStaging))).scalar_one()
    assert fetched.status == "pending"
    assert fetched.rows[0]["model"] == "Teebird"
    assert fetched.plan["counts"]["created"] == 1
    assert fetched.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_import_staging_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.import_staging'`.

- [ ] **Step 3: Create the model and register it**

Create `backend/app/models/import_staging.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.models.base import Base


class ImportStaging(Base):
    __tablename__ = "import_staging"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    filename: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    rows: Mapped[list] = mapped_column(JSONB, nullable=False)
    plan: Mapped[dict] = mapped_column(JSONB, nullable=False)
```

Add to `backend/app/models/__init__.py` — import line and `__all__` entry:

```python
from app.models.import_staging import ImportStaging
```
```python
    "ImportStaging",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_import_staging_model.py -v`
Expected: PASS.

- [ ] **Step 5: Write the Alembic migration**

Create `backend/alembic/versions/f5a6b7c8d9e0_add_import_staging.py`:

```python
"""add_import_staging

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB


revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, Sequence[str], None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'import_staging',
        sa.Column('id', PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            'created_by', PG_UUID(as_uuid=True),
            sa.ForeignKey('users.id'), nullable=False,
        ),
        sa.Column('filename', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('rows', JSONB(), nullable=False),
        sa.Column('plan', JSONB(), nullable=False),
    )
    op.create_index('ix_import_staging_created_by', 'import_staging', ['created_by'])


def downgrade() -> None:
    op.drop_index('ix_import_staging_created_by', table_name='import_staging')
    op.drop_table('import_staging')
```

- [ ] **Step 6: Verify migration applies (upgrade then downgrade)**

Run (copy migration in, reset the test DB to pristine, then cycle):
```
cd backend && docker cp alembic backend_tests:/srv/ \
 && docker exec backend_database psql -U northlanding -d northlanding_test -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;' \
 && docker exec backend_tests sh -c 'cd /srv && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head'
```
Expected: no errors; `import_staging` table created, dropped, recreated. After validating, reset again so pytest owns a clean schema: `docker exec backend_database psql -U northlanding -d northlanding_test -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'`

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/import_staging.py backend/app/models/__init__.py backend/alembic/versions/f5a6b7c8d9e0_add_import_staging.py backend/tests/test_import_staging_model.py
git commit -m "feat(import): add import_staging table and model"
```

---

### Task 4: `ImportStagingRepository`

**Files:**
- Create: `backend/app/repositories/import_staging.py`
- Test: `backend/tests/test_import_staging_repo.py` (create)

**Interfaces:**
- Consumes: `ImportStaging` model.
- Produces: `ImportStagingRepository(db)` with:
  - `async create_pending(*, created_by, filename, rows, plan) -> ImportStaging` (marks the same admin's prior `pending` rows `canceled` first).
  - `async get(staging_id: uuid.UUID) -> ImportStaging | None`
  - `async set_status(staging: ImportStaging, status: str) -> ImportStaging`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_import_staging_repo.py`:

```python
import uuid
from sqlalchemy import select
from app.repositories.import_staging import ImportStagingRepository
from app.models.import_staging import ImportStaging


async def test_create_pending_and_get(db):
    repo = ImportStagingRepository(db)
    admin_id = uuid.uuid4()
    s = await repo.create_pending(
        created_by=admin_id, filename="a.xlsx", rows=[{"x": 1}], plan={"counts": {}},
    )
    fetched = await repo.get(s.id)
    assert fetched is not None
    assert fetched.status == "pending"
    assert fetched.filename == "a.xlsx"


async def test_create_pending_cancels_prior_pending_for_same_admin(db):
    repo = ImportStagingRepository(db)
    admin_id = uuid.uuid4()
    first = await repo.create_pending(created_by=admin_id, filename="1.xlsx", rows=[], plan={})
    await repo.create_pending(created_by=admin_id, filename="2.xlsx", rows=[], plan={})
    refreshed = await repo.get(first.id)
    assert refreshed.status == "canceled"


async def test_create_pending_leaves_other_admins_alone(db):
    repo = ImportStagingRepository(db)
    a, b = uuid.uuid4(), uuid.uuid4()
    first = await repo.create_pending(created_by=a, filename="a.xlsx", rows=[], plan={})
    await repo.create_pending(created_by=b, filename="b.xlsx", rows=[], plan={})
    assert (await repo.get(first.id)).status == "pending"


async def test_set_status(db):
    repo = ImportStagingRepository(db)
    s = await repo.create_pending(created_by=uuid.uuid4(), filename="a.xlsx", rows=[], plan={})
    await repo.set_status(s, "applied")
    assert (await repo.get(s.id)).status == "applied"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_import_staging_repo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.repositories.import_staging'`.

- [ ] **Step 3: Implement the repository**

Create `backend/app/repositories/import_staging.py`:

```python
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.import_staging import ImportStaging


class ImportStagingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_pending(
        self, *, created_by: uuid.UUID, filename: str | None, rows: list, plan: dict
    ) -> ImportStaging:
        # At most one active preview per admin: cancel their prior pending rows.
        await self.db.execute(
            update(ImportStaging)
            .where(
                ImportStaging.created_by == created_by,
                ImportStaging.status == "pending",
            )
            .values(status="canceled")
        )
        staging = ImportStaging(
            created_by=created_by,
            filename=filename,
            status="pending",
            rows=rows,
            plan=plan,
        )
        self.db.add(staging)
        await self.db.flush()
        await self.db.refresh(staging)
        return staging

    async def get(self, staging_id: uuid.UUID) -> ImportStaging | None:
        result = await self.db.execute(
            select(ImportStaging).where(ImportStaging.id == staging_id)
        )
        return result.scalar_one_or_none()

    async def set_status(self, staging: ImportStaging, status: str) -> ImportStaging:
        staging.status = status
        await self.db.flush()
        await self.db.refresh(staging)
        return staging
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_import_staging_repo.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/import_staging.py backend/tests/test_import_staging_repo.py
git commit -m "feat(import): add ImportStagingRepository with cancel-prior semantics"
```

---

### Task 5: Preview / apply / cancel endpoints (replace one-shot import)

**Files:**
- Modify: `backend/app/routers/discs.py` (replace the `import_discs` endpoint at lines ~154-172; update imports)
- Test: `backend/tests/test_import_endpoints.py` (create)

**Interfaces:**
- Consumes: `parse_current_sheet`, `plan_import`, `apply_import`, `row_to_dict`, `row_from_dict` from `app.services.disc_import`; `ImportStagingRepository`.
- Produces endpoints:
  - `POST /discs/import/preview` (multipart `file`) → `{"staging_id": str, "plan": {...}}`; parse failure → 422.
  - `POST /discs/import/{staging_id}/apply` → `{"created", "updated", "skipped", "errors"}`; 404 unknown, 409 not pending.
  - `POST /discs/import/{staging_id}/cancel` → `{"status": "canceled"}`; 404 unknown, 409 not pending.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_import_endpoints.py`:

```python
import io
import uuid
import openpyxl
from datetime import date as _date
from sqlalchemy import select
from app.services.auth import create_access_token
from app.repositories.user import UserRepository
from app.models.disc import Disc
from app.models.pickup_event import SMSJob


def admin_headers(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


async def make_admin(db, email="admin@example.com", google_id="g-admin"):
    repo = UserRepository(db)
    user = await repo.create(name="Admin", email=email, google_id=google_id)
    user.is_admin = True
    await db.commit()
    return user


def _sheet(data_rows):
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


def _files(content):
    return {"file": ("discs.xlsx", content,
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


async def test_preview_returns_plan_and_writes_nothing(client, db):
    admin = await make_admin(db)
    content = _sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", "note",
         None, _date(2026, 6, 6), None, None],
    ])
    resp = await client.post("/discs/import/preview", files=_files(content),
                             headers=admin_headers(admin.id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"]["counts"]["created"] == 1
    assert body["staging_id"]
    # no discs created by preview
    discs = (await db.execute(select(Disc))).scalars().all()
    assert len(discs) == 0


async def test_preview_bad_file_422(client, db):
    admin = await make_admin(db)
    wb = openpyxl.Workbook()
    wb.active.title = "Other"
    buf = io.BytesIO()
    wb.save(buf)
    resp = await client.post("/discs/import/preview", files=_files(buf.getvalue()),
                             headers=admin_headers(admin.id))
    assert resp.status_code == 422


async def test_apply_commits_and_enqueues_sms(client, db):
    admin = await make_admin(db)
    content = _sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", "note",
         None, _date(2026, 6, 6), None, None],
    ])
    preview = await client.post("/discs/import/preview", files=_files(content),
                                headers=admin_headers(admin.id))
    staging_id = preview.json()["staging_id"]
    resp = await client.post(f"/discs/import/{staging_id}/apply",
                             headers=admin_headers(admin.id))
    assert resp.status_code == 200
    assert resp.json()["created"] == 1
    discs = (await db.execute(select(Disc))).scalars().all()
    assert len(discs) == 1
    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert len(jobs) == 2  # welcome + heads-up


async def test_apply_twice_is_409(client, db):
    admin = await make_admin(db)
    content = _sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", "note",
         None, _date(2026, 6, 6), None, None],
    ])
    staging_id = (await client.post("/discs/import/preview", files=_files(content),
                                    headers=admin_headers(admin.id))).json()["staging_id"]
    await client.post(f"/discs/import/{staging_id}/apply", headers=admin_headers(admin.id))
    again = await client.post(f"/discs/import/{staging_id}/apply",
                              headers=admin_headers(admin.id))
    assert again.status_code == 409


async def test_apply_unknown_id_404(client, db):
    admin = await make_admin(db)
    resp = await client.post(f"/discs/import/{uuid.uuid4()}/apply",
                             headers=admin_headers(admin.id))
    assert resp.status_code == 404


async def test_cancel_marks_canceled(client, db):
    admin = await make_admin(db)
    content = _sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", "note",
         None, _date(2026, 6, 6), None, None],
    ])
    staging_id = (await client.post("/discs/import/preview", files=_files(content),
                                    headers=admin_headers(admin.id))).json()["staging_id"]
    resp = await client.post(f"/discs/import/{staging_id}/cancel",
                             headers=admin_headers(admin.id))
    assert resp.status_code == 200
    # applying a canceled import is rejected
    apply = await client.post(f"/discs/import/{staging_id}/apply",
                              headers=admin_headers(admin.id))
    assert apply.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_import_endpoints.py -v`
Expected: FAIL (404s / import errors — new endpoints do not exist).

- [ ] **Step 3: Update imports in `backend/app/routers/discs.py`**

Change the disc_import import line (line ~21) to:

```python
from app.services.disc_import import (
    parse_current_sheet, plan_import, apply_import, row_to_dict, row_from_dict,
)
from app.repositories.import_staging import ImportStagingRepository
```

Confirm `uuid` and `User` are already imported at the top of the file (they are used by other endpoints). `UploadFile`, `File`, `HTTPException` are already imported for the existing import endpoint.

- [ ] **Step 4: Replace the `import_discs` endpoint with three endpoints**

Delete the entire existing `@router.post("/import", ...)` `import_discs` function (lines ~154-172) and put in its place:

```python
@router.post("/import/preview", operation_id="previewImportDiscs")
async def preview_import_discs(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    content = await file.read()
    try:
        rows = parse_current_sheet(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    plan = await plan_import(rows, db)
    repo = ImportStagingRepository(db)
    staging = await repo.create_pending(
        created_by=user.id,
        filename=file.filename,
        rows=[row_to_dict(r) for r in rows],
        plan=plan.to_dict(),
    )
    await db.commit()
    return {"staging_id": str(staging.id), "plan": plan.to_dict()}


@router.post("/import/{staging_id}/apply", operation_id="applyImportDiscs")
async def apply_import_discs(
    staging_id: uuid.UUID,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = ImportStagingRepository(db)
    staging = await repo.get(staging_id)
    if staging is None:
        raise HTTPException(status_code=404, detail="Import not found")
    if staging.status != "pending":
        raise HTTPException(status_code=409, detail="Import already resolved")
    rows = [row_from_dict(d) for d in staging.rows]
    summary = await apply_import(rows, db)
    await repo.set_status(staging, "applied")
    await db.commit()
    return {
        "created": summary.created,
        "updated": summary.updated,
        "skipped": summary.skipped,
        "errors": summary.errors,
    }


@router.post("/import/{staging_id}/cancel", operation_id="cancelImportDiscs")
async def cancel_import_discs(
    staging_id: uuid.UUID,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = ImportStagingRepository(db)
    staging = await repo.get(staging_id)
    if staging is None:
        raise HTTPException(status_code=404, detail="Import not found")
    if staging.status != "pending":
        raise HTTPException(status_code=409, detail="Import already resolved")
    await repo.set_status(staging, "canceled")
    await db.commit()
    return {"status": "canceled"}
```

Note: if `Annotated` is not already imported in `discs.py`, add `from typing import Annotated` at the top (check first — most routers already import it).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_import_endpoints.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Run the full backend suite (no regressions)**

Run: `cd backend && uv run pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/discs.py backend/tests/test_import_endpoints.py
git commit -m "feat(import): replace one-shot import with preview/apply/cancel endpoints"
```

---

### Task 6: Frontend preview dialog + wire AdminDiscsPage

**Files:**
- Create: `frontend/src/components/ImportPreviewDialog.tsx`
- Create: `frontend/src/components/ImportPreviewDialog.test.tsx`
- Modify: `frontend/src/pages/AdminDiscsPage.tsx` (`handleImportFile` + dialog state + render)

**Interfaces:**
- Consumes: backend `preview` response `{ staging_id: string, plan: ImportPlan }`.
- Produces (component): `ImportPreviewDialog` props `{ open: boolean; filename: string; plan: ImportPlan | null; busy: boolean; onApprove: () => void; onCancel: () => void }`.
- Produces (shared type in the component file, exported): `ImportPlan`.

- [ ] **Step 1: Write the failing component test**

Create `frontend/src/components/ImportPreviewDialog.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'
import { ImportPreviewDialog, type ImportPlan } from './ImportPreviewDialog'

const plan: ImportPlan = {
  created: [{ row_number: 4, manufacturer: 'Discraft', model: 'Heat', colors: ['purple'], owner: 'Jane Doe / +14049518881' }],
  updated: [{ row_number: 5, manufacturer: 'Innova', model: 'Roc', colors: ['blue'], owner: null,
    diffs: [{ field: 'notes', old: 'x', new: 'changed' }] }],
  unchanged: 3,
  errors: [{ row: { row_number: 7, manufacturer: 'Axiom', model: 'Fireball', notes: 'x' }, reason: 'missing or invalid Date found' }],
  counts: { created: 1, updated: 1, unchanged: 3, errors: 1 },
}

test('renders counts, buckets, diffs, and full error rows', () => {
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={plan} busy={false}
    onApprove={() => {}} onCancel={() => {}} />)
  expect(screen.getByText(/1 new/i)).toBeInTheDocument()
  expect(screen.getByText(/1 updated/i)).toBeInTheDocument()
  expect(screen.getByText(/3 unchanged/i)).toBeInTheDocument()
  expect(screen.getByText(/1 error/i)).toBeInTheDocument()
  expect(screen.getByText('Heat')).toBeInTheDocument()
  expect(screen.getByText(/notes/i)).toBeInTheDocument()
  expect(screen.getByText(/changed/)).toBeInTheDocument()
  expect(screen.getByText(/missing or invalid Date found/)).toBeInTheDocument()
  expect(screen.getByText('Fireball')).toBeInTheDocument()
})

test('approve and cancel fire their handlers', () => {
  const onApprove = vi.fn()
  const onCancel = vi.fn()
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={plan} busy={false}
    onApprove={onApprove} onCancel={onCancel} />)
  fireEvent.click(screen.getByRole('button', { name: /approve & merge/i }))
  expect(onApprove).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }))
  expect(onCancel).toHaveBeenCalledOnce()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/ImportPreviewDialog.test.tsx`
Expected: FAIL — module `./ImportPreviewDialog` does not exist.

- [ ] **Step 3: Implement the dialog component**

Create `frontend/src/components/ImportPreviewDialog.tsx`:

```tsx
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

export type PlanDiff = { field: string; old: unknown; new: unknown }
export type PlannedNew = {
  row_number: number
  manufacturer: string
  model: string
  colors: string[]
  owner: string | null
}
export type PlannedUpdate = PlannedNew & { diffs: PlanDiff[] }
export type PlanError = { row: Record<string, unknown>; reason: string }
export type ImportPlan = {
  created: PlannedNew[]
  updated: PlannedUpdate[]
  unchanged: number
  errors: PlanError[]
  counts: { created: number; updated: number; unchanged: number; errors: number }
}

const fmt = (v: unknown): string =>
  v === null || v === undefined ? '—' : Array.isArray(v) ? v.join(' ') : String(v)

const ERROR_COLS = [
  'row_number', 'first_name', 'last_name', 'phone', 'manufacturer',
  'model', 'colors', 'notes', 'input_date', 'returned', 'returned_date',
]

export function ImportPreviewDialog({
  open,
  filename,
  plan,
  busy,
  onApprove,
  onCancel,
}: {
  open: boolean
  filename: string
  plan: ImportPlan | null
  busy: boolean
  onApprove: () => void
  onCancel: () => void
}) {
  if (!plan) return null
  const c = plan.counts
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel() }}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Review import — {filename}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-wrap gap-2 text-sm">
          <span className="rounded bg-muted px-2 py-1">{c.created} new</span>
          <span className="rounded bg-muted px-2 py-1">{c.updated} updated</span>
          <span className="rounded bg-muted px-2 py-1">{c.unchanged} unchanged</span>
          <span className="rounded bg-muted px-2 py-1">{c.errors} error{c.errors === 1 ? '' : 's'}</span>
        </div>

        {plan.created.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer font-medium">New discs ({plan.created.length})</summary>
            <ul className="mt-1 space-y-1 text-sm">
              {plan.created.map((d) => (
                <li key={`c-${d.row_number}`}>
                  {d.manufacturer} {d.model} [{d.colors.join(' ')}] {d.owner ? `— ${d.owner}` : ''}
                </li>
              ))}
            </ul>
          </details>
        )}

        {plan.updated.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer font-medium">Updated discs ({plan.updated.length})</summary>
            <ul className="mt-1 space-y-2 text-sm">
              {plan.updated.map((d) => (
                <li key={`u-${d.row_number}`}>
                  <div>{d.manufacturer} {d.model} [{d.colors.join(' ')}]</div>
                  <ul className="ml-4 list-disc text-muted-foreground">
                    {d.diffs.map((diff, i) => (
                      <li key={i}>{diff.field}: {fmt(diff.old)} → {fmt(diff.new)}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </details>
        )}

        {plan.errors.length > 0 && (
          <div className="mt-2">
            <p className="font-medium text-destructive">Error rows ({plan.errors.length})</p>
            <div className="overflow-x-auto">
              <table className="mt-1 w-full border-collapse text-xs">
                <thead>
                  <tr>
                    {ERROR_COLS.map((col) => (
                      <th key={col} className="border px-1 py-0.5 text-left">{col}</th>
                    ))}
                    <th className="border px-1 py-0.5 text-left">reason</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.errors.map((e, i) => (
                    <tr key={i}>
                      {ERROR_COLS.map((col) => (
                        <td key={col} className="border px-1 py-0.5">{fmt(e.row[col])}</td>
                      ))}
                      <td className="border px-1 py-0.5 text-destructive">{e.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button onClick={onApprove} disabled={busy}>Approve &amp; merge</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/ImportPreviewDialog.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Wire the dialog into AdminDiscsPage**

In `frontend/src/pages/AdminDiscsPage.tsx`:

Add the import near the other component imports:

```tsx
import { ImportPreviewDialog, type ImportPlan } from '../components/ImportPreviewDialog'
```

Add state next to `const [importMsg, setImportMsg] = useState('')`:

```tsx
  const [preview, setPreview] = useState<{ stagingId: string; plan: ImportPlan; filename: string } | null>(null)
  const [importBusy, setImportBusy] = useState(false)
```

Replace the existing `handleImportFile` function with a preview-first version, and add approve/cancel handlers:

```tsx
  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setImportMsg('')
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await axiosInstance.post('/discs/import/preview', form)
      const data = res.data as { staging_id: string; plan: ImportPlan }
      setPreview({ stagingId: data.staging_id, plan: data.plan, filename: file.name })
    } catch {
      setImportMsg('Preview failed. Check the file and try again.')
    } finally {
      e.target.value = ''
    }
  }

  async function handleApproveImport() {
    if (!preview) return
    setImportBusy(true)
    try {
      const res = await axiosInstance.post(`/discs/import/${preview.stagingId}/apply`)
      const s = res.data as { created: number; updated: number; skipped: number; errors: unknown[] }
      setImportMsg(`Imported: ${s.created} new, ${s.updated} updated, ${s.skipped} unchanged, ${s.errors.length} errors`)
      await queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
      setPreview(null)
    } catch {
      setImportMsg('Import failed. Please try again.')
    } finally {
      setImportBusy(false)
    }
  }

  async function handleCancelImport() {
    if (!preview) return
    setImportBusy(true)
    try {
      await axiosInstance.post(`/discs/import/${preview.stagingId}/cancel`)
    } catch {
      // best-effort discard; the staged row is superseded on next preview anyway
    } finally {
      setImportBusy(false)
      setPreview(null)
    }
  }
```

Render the dialog. Place it just inside the top-level `<div>` of the returned JSX (e.g. immediately after `<PageHeader ... />`):

```tsx
      <ImportPreviewDialog
        open={preview !== null}
        filename={preview?.filename ?? ''}
        plan={preview?.plan ?? null}
        busy={importBusy}
        onApprove={handleApproveImport}
        onCancel={handleCancelImport}
      />
```

- [ ] **Step 6: Run the existing page test (no regression)**

Run: `cd frontend && npx vitest run src/pages/AdminDiscsPage.test.tsx`
Expected: PASS (the existing filter-bar test still passes; the dialog is closed by default).

- [ ] **Step 7: Typecheck and build**

Run: `cd frontend && npx tsc -b`
Expected: no type errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/ImportPreviewDialog.tsx frontend/src/components/ImportPreviewDialog.test.tsx frontend/src/pages/AdminDiscsPage.tsx
git commit -m "feat(import): admin preview dialog with approve/cancel flow"
```

---

## Self-Review

**Spec coverage:**
- Counts (new/updated/unchanged) → `plan_import` + `ImportPlan.to_dict().counts` (Task 2), rendered as tiles (Task 6). ✅
- Approval before merge/SMS → staging + apply endpoint; preview writes nothing, apply does the writes/SMS (Tasks 2, 4, 5). ✅
- Browse which discs are new/updated with old→new diffs → `created`/`updated` lists + `_plan_diffs`, expandable sections (Tasks 2, 6). ✅
- Full error-row contents + reason → `errors` carry `row_to_dict` output; error table renders all columns (Tasks 2, 6). ✅
- Server-side staging in a JSONB row in a new table → `import_staging` model/migration/repo (Tasks 3, 4). ✅
- One active preview per admin (cancel-prior) → `create_pending` (Task 4). ✅
- Replace one-shot endpoint → old `import_discs` deleted (Task 5). ✅
- Apply behavior unchanged → Task 1 is behavior-preserving; existing `test_disc_import.py` still passes. ✅
- Testing: plan no-write/no-SMS asserted (Task 2); endpoint apply enqueues SMS + 409/404 (Task 5); migration up/down (Task 3); frontend dialog + no page regression (Task 6). ✅

**Placeholder scan:** No TBD/TODO; every code step is complete. ✅

**Type consistency:** `plan_import`/`apply_import`/`row_to_dict`/`row_from_dict`/`_compute_updates` names consistent across Tasks 1-5. Frontend `ImportPlan` shape matches `ImportPlan.to_dict()` (created/updated/unchanged/errors/counts; updated items carry `diffs`; errors carry `{row, reason}`). Endpoint response keys (`staging_id`, `plan`, `created`/`updated`/`skipped`/`errors`) match frontend consumers. ✅

**Note (non-blocking):** the working tree has an untracked `backend/this.sh` containing live Surge secrets. It is not part of this feature and is not committed by any task — recommend the user delete it / keep it out of git.
