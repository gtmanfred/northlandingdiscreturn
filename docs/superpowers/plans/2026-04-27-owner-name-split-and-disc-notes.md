# Owner First/Last Name Split + Disc Notes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `owners.name` into `first_name`/`last_name`, add a comma-aware parser used by the import script and admin form, and add an admin-only `notes` field on discs (also writable by users on their own wishlist entries).

**Architecture:** One Alembic migration covers both DB changes (split name, drop unique constraint, add `discs.notes`). A small `parse_owner_name` helper centralizes the comma/space rule on the backend; the same logic is duplicated in TypeScript for the wishlist UI and in the import script (which talks HTTP, not DB). API schemas swap `owner_name` → `owner_first_name` + `owner_last_name`; `OwnerOut` exposes a computed `name` for display compatibility. `DiscOut.notes` is filtered to `None` only on `GET /me/discs`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, Pydantic v2, React 18 + TS, Orval-generated client.

Spec: `docs/superpowers/specs/2026-04-27-owner-name-split-and-disc-notes-design.md`

## File Structure

**New files:**
- `backend/app/owner_name.py` — `parse_owner_name` helper.
- `backend/tests/test_owner_name.py` — parser unit tests.
- `backend/alembic/versions/<rev>_split_owner_name_and_disc_notes.py` — schema migration.
- `frontend/src/utils/ownerName.ts` — TS port of the parser.
- `frontend/src/utils/ownerName.test.ts` — TS parser tests.

**Modified files:**
- `backend/app/models/owner.py` — drop `name`, add `first_name`/`last_name`, drop unique constraint, swap index.
- `backend/app/models/disc.py` — add `notes`.
- `backend/app/schemas/owner.py` — `first_name`/`last_name` + computed `name`.
- `backend/app/schemas/disc.py` — `owner_first_name`/`owner_last_name`, `notes`, `WishlistDiscCreate.notes`.
- `backend/app/repositories/owner.py` — new `resolve_or_create` signature, two suggestion endpoints, name-prefix lookup.
- `backend/app/repositories/disc.py` — owner_name filter joins on `first_name || ' ' || last_name`.
- `backend/app/routers/discs.py` — handle new owner fields, persist `notes`.
- `backend/app/routers/users.py` — wishlist passes user's name through `parse_owner_name`, persists `notes`, strips `notes` on `/me/discs`.
- `backend/app/routers/suggestions.py` — replace `owner_name` field with `owner_first_name`/`owner_last_name`; phone suggestion takes both names.
- `backend/tests/test_owners.py`, `test_discs.py`, `test_suggestions.py`, `test_users.py`, `test_admin.py` — update for new shape.
- `scripts/import_discs.py` — comma-aware parse, send split fields.
- `frontend/openapi.json`, `frontend/src/api/northlanding.ts` — regenerated.
- `frontend/src/pages/AdminDiscFormPage.tsx` — two name inputs, notes textarea.
- `frontend/src/pages/AdminDiscsPage.tsx` — show notes, owner display uses computed `name`.
- `frontend/src/pages/MyWishlistPage.tsx` — notes input + display, send split owner name.

---

## Task 1: Backend `parse_owner_name` helper (TDD)

**Files:**
- Create: `backend/app/owner_name.py`
- Create: `backend/tests/test_owner_name.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_owner_name.py`:

```python
import pytest
from app.owner_name import parse_owner_name


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Doe, John", ("Doe", "John")),
        ("  Doe ,  John  ", ("Doe", "John")),
        ("John Smith", ("John", "Smith")),
        ("Mary Jane Watson", ("Mary", "Jane Watson")),
        ("Cher", ("Cher", "")),
        ("", ("", "")),
        ("   ", ("", "")),
        ("a, b, c", ("a", "b, c")),
        ("  Solo  ", ("Solo", "")),
    ],
)
def test_parse_owner_name(raw, expected):
    assert parse_owner_name(raw) == expected
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `cd backend && teststack run tests -- tests/test_owner_name.py -v`
Expected: ImportError / FAIL — `app.owner_name` module not found.

- [ ] **Step 3: Implement helper**

Create `backend/app/owner_name.py`:

```python
def parse_owner_name(raw: str) -> tuple[str, str]:
    """Parse a freeform name into (first_name, last_name).

    Comma takes priority — first name is in front of the comma:
        "Doe, John" -> ("Doe", "John")
    Otherwise split on the first whitespace run:
        "John Smith" -> ("John", "Smith")
        "Cher"       -> ("Cher", "")
    Empty / whitespace-only input returns ("", "").
    """
    if raw is None:
        return ("", "")
    s = raw.strip()
    if not s:
        return ("", "")
    if "," in s:
        first, _, last = s.partition(",")
        return (first.strip(), last.strip())
    parts = s.split(None, 1)
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[1].strip())
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `cd backend && teststack run tests -- tests/test_owner_name.py -v`
Expected: 9 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/owner_name.py backend/tests/test_owner_name.py
git commit -m "feat(owner): add parse_owner_name helper"
```

---

## Task 2: Owner model — split name, drop unique constraint

**Files:**
- Modify: `backend/app/models/owner.py`
- Modify: `backend/tests/test_owners.py:5-27` (replace existing model tests)

- [ ] **Step 1: Replace the two model tests**

In `backend/tests/test_owners.py`, replace `test_owner_model_persists` and **delete** `test_owner_unique_name_phone` (no longer applicable). Also update **every** call to `Owner(name=...)` and `OwnerRepository.resolve_or_create(name=...)` in this file (and its test bodies that compare `o.name == "..."`) to use the new triple. Use this find/replace approach:

Replace the existing `test_owner_model_persists` with:

```python
async def test_owner_model_persists(db):
    owner = Owner(first_name="John", last_name="Smith", phone_number="+15551234567")
    db.add(owner)
    await db.flush()
    await db.refresh(owner)
    assert isinstance(owner.id, uuid.UUID)
    assert owner.first_name == "John"
    assert owner.last_name == "Smith"
    assert owner.phone_number == "+15551234567"
    assert owner.heads_up_sent_at is None
    assert owner.created_at is not None


async def test_owner_allows_duplicate_triple(db):
    """Uniqueness is enforced at the application layer, not the DB."""
    db.add(Owner(first_name="Jane", last_name="Doe", phone_number="+15550001111"))
    await db.flush()
    db.add(Owner(first_name="Jane", last_name="Doe", phone_number="+15550001111"))
    await db.flush()  # must NOT raise
```

Delete the old `test_owner_unique_name_phone`. Leave the other tests in this file failing for now — Task 3 fixes the repo and Task 8 fixes the rest.

- [ ] **Step 2: Update the model**

Replace `backend/app/models/owner.py` with:

```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class Owner(Base):
    __tablename__ = "owners"
    __table_args__ = (
        Index("ix_owners_phone_number", "phone_number"),
        Index("ix_owners_last_first", "last_name", "first_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    phone_number: Mapped[str] = mapped_column(String, nullable=False)
    heads_up_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    discs: Mapped[list["Disc"]] = relationship(back_populates="owner")

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
```

- [ ] **Step 3: Add `notes` to Disc model**

In `backend/app/models/disc.py`, add the column inside the `Disc` class, after `final_notice_sent`:

```python
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 4: Commit (model only — migration follows)**

```bash
git add backend/app/models/owner.py backend/app/models/disc.py backend/tests/test_owners.py
git commit -m "refactor(owner): split name into first_name/last_name; add disc.notes"
```

(Tests will not pass yet. The migration in Task 3 makes them runnable.)

---

## Task 3: Alembic migration

**Files:**
- Create: `backend/alembic/versions/<auto-generated>_split_owner_name_and_disc_notes.py`

- [ ] **Step 1: Generate the empty revision**

Run: `cd backend && uv run alembic revision -m "split owner name and disc notes"`
Expected: prints the new file path. Open it.

- [ ] **Step 2: Replace the body**

Set `down_revision = "485472f19d21"` (latest head). Use this content:

```python
"""split owner name and disc notes

Revision ID: <keep generated>
Revises: 485472f19d21
Create Date: <keep generated>
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "<keep generated>"
down_revision: Union[str, Sequence[str], None] = "485472f19d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the new owner name columns (nullable for backfill).
    op.add_column("owners", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column(
        "owners",
        sa.Column("last_name", sa.String(), nullable=False, server_default=""),
    )

    # 2. Backfill: split existing `name` on the first space.
    #    "John Smith"        -> first="John", last="Smith"
    #    "Mary Jane Watson"  -> first="Mary", last="Jane Watson"
    #    "Cher"              -> first="Cher", last=""
    op.execute(
        """
        UPDATE owners
        SET
            first_name = CASE
                WHEN position(' ' in name) = 0 THEN name
                ELSE substring(name from 1 for position(' ' in name) - 1)
            END,
            last_name = CASE
                WHEN position(' ' in name) = 0 THEN ''
                ELSE trim(substring(name from position(' ' in name) + 1))
            END
        """
    )

    # 3. Lock first_name to NOT NULL after backfill.
    op.alter_column("owners", "first_name", nullable=False)

    # 4. Drop old uniqueness, name index, and the column itself.
    op.drop_constraint("uq_owners_name_phone", "owners", type_="unique")
    op.drop_index("ix_owners_name", table_name="owners")
    op.drop_column("owners", "name")

    # 5. New composite index for autocomplete / sorted listing.
    op.create_index(
        "ix_owners_last_first", "owners", ["last_name", "first_name"]
    )

    # 6. Disc notes column.
    op.add_column("discs", sa.Column("notes", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("discs", "notes")
    op.drop_index("ix_owners_last_first", table_name="owners")
    op.add_column("owners", sa.Column("name", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE owners
        SET name = CASE
            WHEN last_name = '' THEN first_name
            ELSE first_name || ' ' || last_name
        END
        """
    )
    op.alter_column("owners", "name", nullable=False)
    op.create_index("ix_owners_name", "owners", ["name"])
    op.create_unique_constraint(
        "uq_owners_name_phone", "owners", ["name", "phone_number"]
    )
    op.drop_column("owners", "last_name")
    op.drop_column("owners", "first_name")
```

- [ ] **Step 3: Smoke-test the migration on local Postgres**

Run: `cd backend && uv run alembic upgrade head`
Expected: applies cleanly. Then `uv run alembic downgrade -1` and `uv run alembic upgrade head` again — round-trip clean.

- [ ] **Step 4: Run model-only tests for the new schema**

Run: `cd backend && teststack run tests -- tests/test_owners.py::test_owner_model_persists tests/test_owners.py::test_owner_allows_duplicate_triple -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/*split_owner_name_and_disc_notes*.py
git commit -m "feat(db): split owners.name into first/last, drop unique, add discs.notes"
```

---

## Task 4: OwnerRepository update

**Files:**
- Modify: `backend/app/repositories/owner.py`

- [ ] **Step 1: Replace the file**

```python
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.owner import Owner


class OwnerRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_or_create(
        self, *, first_name: str, last_name: str, phone_number: str
    ) -> Owner:
        result = await self.db.execute(
            select(Owner).where(
                Owner.first_name == first_name,
                Owner.last_name == last_name,
                Owner.phone_number == phone_number,
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

    async def get_by_id(self, owner_id: uuid.UUID) -> Owner | None:
        result = await self.db.execute(select(Owner).where(Owner.id == owner_id))
        return result.scalar_one_or_none()

    async def list_by_phones(self, phone_numbers: list[str]) -> list[Owner]:
        if not phone_numbers:
            return []
        result = await self.db.execute(
            select(Owner).where(Owner.phone_number.in_(phone_numbers))
        )
        return list(result.scalars().all())

    async def mark_heads_up_sent(self, owner: Owner) -> Owner:
        owner.heads_up_sent_at = func.now()
        await self.db.flush()
        await self.db.refresh(owner)
        return owner

    async def suggest_first_names(self, limit: int = 200) -> list[str]:
        result = await self.db.execute(
            select(Owner.first_name)
            .where(Owner.first_name != "")
            .distinct()
            .order_by(func.lower(Owner.first_name))
            .limit(limit)
        )
        return [row[0] for row in result.all()]

    async def suggest_last_names(self, limit: int = 200) -> list[str]:
        result = await self.db.execute(
            select(Owner.last_name)
            .where(Owner.last_name != "")
            .distinct()
            .order_by(func.lower(Owner.last_name))
            .limit(limit)
        )
        return [row[0] for row in result.all()]

    async def list_phones_for_name(
        self, *, first_name: str, last_name: str
    ) -> list[str]:
        """Phones for owners matching both prefixes (case-insensitive)."""
        stmt = select(Owner.phone_number).distinct()
        if first_name:
            stmt = stmt.where(Owner.first_name.ilike(first_name))
        if last_name:
            stmt = stmt.where(Owner.last_name.ilike(last_name))
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]
```

- [ ] **Step 2: Update existing repo tests in `test_owners.py`**

In `backend/tests/test_owners.py`, replace every call of `resolve_or_create(name="X", ...)` with split fields, and every assertion `o.name == "X"` with the appropriate `first_name`/`last_name`. Concrete substitutions:

| Old call | New call |
|---|---|
| `Owner(name="Ada", phone_number=...)` | `Owner(first_name="Ada", last_name="", phone_number=...)` |
| `resolve_or_create(name="Jill", phone_number="+1...")` | `resolve_or_create(first_name="Jill", last_name="", phone_number="+1...")` |
| `resolve_or_create(name="Jack", ...)` | `resolve_or_create(first_name="Jack", last_name="", ...)` |
| `resolve_or_create(name="A", ...)` etc. | use `first_name="A", last_name=""` |
| `resolve_or_create(name="Eva", ...)` | `first_name="Eva", last_name=""` |
| `assert out.owner.name == "Eva"` | keep as-is — `OwnerOut.name` is still computed |

For multi-word fixtures like `"John Smith"`, use `first_name="John", last_name="Smith"`.

- [ ] **Step 3: Run owner tests**

Run: `cd backend && teststack run tests -- tests/test_owners.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/repositories/owner.py backend/tests/test_owners.py
git commit -m "refactor(owner): repository takes first/last name; add suggest_*_names"
```

---

## Task 5: Schemas — owner, disc, wishlist

**Files:**
- Modify: `backend/app/schemas/owner.py`
- Modify: `backend/app/schemas/disc.py`

- [ ] **Step 1: Update `OwnerOut`**

Replace `backend/app/schemas/owner.py`:

```python
import uuid
from datetime import datetime
from pydantic import BaseModel, computed_field


class OwnerOut(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    phone_number: str
    heads_up_sent_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
```

- [ ] **Step 2: Update `DiscCreate`, `DiscUpdate`, `DiscOut`, `WishlistDiscCreate`**

In `backend/app/schemas/disc.py`:

Replace the four classes (keep `DiscPhotoOut` and `DiscPage` unchanged):

```python
class DiscOut(BaseModel):
    id: uuid.UUID
    manufacturer: str
    name: str
    color: str
    owner: OwnerOut | None = None
    is_clear: bool
    input_date: date
    is_found: bool
    is_returned: bool
    final_notice_sent: bool
    notes: str | None = None
    photos: list[DiscPhotoOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscCreate(BaseModel):
    manufacturer: str
    name: str
    color: str
    input_date: date
    owner_first_name: str | None = None
    owner_last_name: str | None = None
    phone_number: str | None = None
    notes: str | None = None
    is_clear: bool = False
    is_found: bool = True

    @field_validator("phone_number")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        return normalize_phone(v) if v else None

    @model_validator(mode="after")
    def owner_fields_together(self) -> "DiscCreate":
        # All three owner fields are present-or-absent together. Empty-string
        # last_name is valid (single-token names) when first_name + phone are set.
        provided = (
            self.owner_first_name is not None,
            self.owner_last_name is not None,
            self.phone_number is not None,
        )
        if any(provided) and not all(provided):
            raise ValueError(
                "owner_first_name, owner_last_name, and phone_number must be "
                "provided together or not at all"
            )
        return self


class DiscUpdate(BaseModel):
    manufacturer: str | None = None
    name: str | None = None
    color: str | None = None
    owner_first_name: str | None = None
    owner_last_name: str | None = None
    phone_number: str | None = None
    notes: str | None = None
    is_clear: bool | None = None
    is_found: bool | None = None
    is_returned: bool | None = None

    @field_validator("phone_number")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        return normalize_phone(v) if v else None


class WishlistDiscCreate(BaseModel):
    manufacturer: str | None = None
    name: str | None = None
    color: str | None = None
    phone_number: str
    owner_first_name: str | None = None
    owner_last_name: str | None = None
    notes: str | None = None

    @field_validator("phone_number")
    @classmethod
    def normalize(cls, v: str) -> str:
        return normalize_phone(v)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/owner.py backend/app/schemas/disc.py
git commit -m "refactor(api): split owner name fields and add disc notes"
```

---

## Task 6: Disc repository — owner_name filter joins on full name

**Files:**
- Modify: `backend/app/repositories/disc.py:47-119`

- [ ] **Step 1: Replace the two `owner_name` filter blocks**

Replace the body of `list_all` and `count_all` filter clauses on `owner_name`. In both methods, change:

```python
if owner_name is not None:
    stmt = stmt.join(Owner, Disc.owner_id == Owner.id).where(
        Owner.name.ilike(f"%{owner_name}%")
    )
```

to:

```python
if owner_name is not None:
    stmt = stmt.join(Owner, Disc.owner_id == Owner.id).where(
        func.concat(Owner.first_name, " ", Owner.last_name).ilike(f"%{owner_name}%")
    )
```

`func` is already imported at the top of the file. The `Owner` import inside both methods stays.

- [ ] **Step 2: Commit (no test change yet — covered in Task 8)**

```bash
git add backend/app/repositories/disc.py
git commit -m "refactor(discs): owner_name filter searches concatenated first+last"
```

---

## Task 7: Routers — discs, users, suggestions

**Files:**
- Modify: `backend/app/routers/discs.py`
- Modify: `backend/app/routers/users.py`
- Modify: `backend/app/routers/suggestions.py`

- [ ] **Step 1: `routers/discs.py` — `create_disc`**

Replace the `create_disc` handler body (`POST /discs`):

```python
@router.post("", response_model=DiscOut, status_code=201, operation_id="createDisc")
async def create_disc(
    body: DiscCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = DiscRepository(db)
    owner_id = None
    owner_obj = None
    if (
        body.owner_first_name is not None
        and body.owner_last_name is not None
        and body.phone_number
    ):
        owner_obj = await OwnerRepository(db).resolve_or_create(
            first_name=body.owner_first_name,
            last_name=body.owner_last_name,
            phone_number=body.phone_number,
        )
        owner_id = owner_obj.id

    disc = await repo.create(
        manufacturer=body.manufacturer,
        name=body.name,
        color=body.color,
        input_date=body.input_date,
        owner_id=owner_id,
        is_clear=body.is_clear,
        is_found=body.is_found,
        notes=body.notes,
    )

    if owner_obj is not None:
        await maybe_enqueue_heads_up(owner=owner_obj, is_found=disc.is_found, db=db)

    await db.commit()
    return await repo.get_by_id(disc.id)
```

- [ ] **Step 2: Add `notes` parameter to `DiscRepository.create`**

In `backend/app/repositories/disc.py`, update `create`:

```python
async def create(
    self,
    *,
    manufacturer: str,
    name: str,
    color: str,
    input_date: date,
    owner_id: uuid.UUID | None = None,
    is_clear: bool = False,
    is_found: bool = True,
    notes: str | None = None,
) -> Disc:
    disc = Disc(
        manufacturer=manufacturer,
        name=name,
        color=color,
        input_date=input_date,
        owner_id=owner_id,
        is_clear=is_clear,
        is_found=is_found,
        notes=notes,
    )
    self.db.add(disc)
    await self.db.flush()
    await self.db.refresh(disc)
    return disc
```

- [ ] **Step 3: `routers/discs.py` — `update_disc`**

Replace the `update_disc` handler body:

```python
@router.patch("/{disc_id}", response_model=DiscOut, operation_id="updateDisc")
async def update_disc(
    disc_id: uuid.UUID,
    body: DiscUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = DiscRepository(db)
    disc = await repo.get_by_id(disc_id)
    if disc is None:
        raise HTTPException(status_code=404, detail="Disc not found")

    payload = body.model_dump(exclude_unset=True)
    owner_first = payload.pop("owner_first_name", None)
    owner_last = payload.pop("owner_last_name", None)
    phone = payload.pop("phone_number", None)

    fields_set = body.model_fields_set
    owner_fields_touched = bool(
        fields_set & {"owner_first_name", "owner_last_name", "phone_number"}
    )
    if owner_fields_touched:
        cur = disc.owner
        eff_first = owner_first if "owner_first_name" in fields_set else (cur.first_name if cur else None)
        eff_last = owner_last if "owner_last_name" in fields_set else (cur.last_name if cur else None)
        eff_phone = phone if "phone_number" in fields_set else (cur.phone_number if cur else None)
        if eff_first is not None and eff_last is not None and eff_phone:
            new_owner = await OwnerRepository(db).resolve_or_create(
                first_name=eff_first,
                last_name=eff_last,
                phone_number=eff_phone,
            )
            payload["owner_id"] = new_owner.id
        else:
            payload["owner_id"] = None

    if not payload:
        raise HTTPException(status_code=422, detail="No fields provided for update")

    await repo.update(disc, **payload)
    await db.commit()
    return await repo.get_by_id(disc_id)
```

- [ ] **Step 4: `routers/users.py` — wishlist endpoints**

Add the import at top: `from app.owner_name import parse_owner_name`.

Replace the `add_wishlist_disc` handler:

```python
@router.post("/me/wishlist", response_model=DiscOut, status_code=201, operation_id="addWishlistDisc")
async def add_wishlist_disc(
    body: WishlistDiscCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    verified = await UserRepository(db).get_verified_numbers(current_user.id)
    verified_strs = [p.number for p in verified]
    if body.phone_number not in verified_strs:
        raise HTTPException(status_code=400, detail="Phone number not verified on your account")
    if body.owner_first_name is not None and body.owner_last_name is not None:
        first, last = body.owner_first_name, body.owner_last_name
    else:
        first, last = parse_owner_name(current_user.name or "")
    owner = await OwnerRepository(db).resolve_or_create(
        first_name=first, last_name=last, phone_number=body.phone_number
    )
    disc = await DiscRepository(db).create(
        manufacturer=body.manufacturer or "",
        name=body.name or "",
        color=body.color or "",
        input_date=date.today(),
        owner_id=owner.id,
        is_found=False,
        notes=body.notes,
    )
    await db.commit()
    return await DiscRepository(db).get_by_id(disc.id)
```

Replace `get_my_discs` to strip notes:

```python
@router.get("/me/discs", response_model=list[DiscOut], operation_id="getMyDiscs")
async def get_my_discs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    phones = await UserRepository(db).get_verified_numbers(current_user.id)
    numbers = [p.number for p in phones]
    owners = await OwnerRepository(db).list_by_phones(numbers)
    discs = await DiscRepository(db).list_found_by_owner_ids([o.id for o in owners])
    out = [DiscOut.model_validate(d) for d in discs]
    for d in out:
        d.notes = None
    return out
```

(Leave `get_my_wishlist` returning the raw discs — `notes` flows through.)

- [ ] **Step 5: `routers/suggestions.py` — replace `owner_name` field**

Replace the file:

```python
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models.disc import Disc
from app.models.owner import Owner
from app.models.user import PhoneNumber, User
from app.repositories.owner import OwnerRepository

router = APIRouter()

SuggestionField = Literal[
    "manufacturer", "name", "color", "owner_first_name", "owner_last_name"
]


@router.get("", response_model=list[str], operation_id="getSuggestions")
async def get_suggestions(
    field: Annotated[SuggestionField, Query()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[str]:
    if field in ("owner_first_name", "owner_last_name"):
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin required")
        repo = OwnerRepository(db)
        if field == "owner_first_name":
            return await repo.suggest_first_names()
        return await repo.suggest_last_names()

    col = getattr(Disc, field)
    subq = (
        select(distinct(col).label("val"))
        .where(col.is_not(None))
        .where(col != "")
        .subquery()
    )
    result = await db.execute(select(subq.c.val).order_by(func.lower(subq.c.val)))
    return [row[0] for row in result.all()]


class PhoneSuggestion(BaseModel):
    number: str
    label: str


@router.get("/phone", response_model=list[PhoneSuggestion], operation_id="getPhoneSuggestions")
async def get_phone_suggestions(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    owner_first_name: Annotated[str, Query()] = "",
    owner_last_name: Annotated[str, Query()] = "",
) -> list[PhoneSuggestion]:
    if not owner_first_name and not owner_last_name:
        return []

    full_name = f"{owner_first_name} {owner_last_name}".strip()
    registered: dict[str, PhoneSuggestion] = {}

    if full_name:
        registered_result = await db.execute(
            select(PhoneNumber.number, User.name, User.email)
            .join(User, PhoneNumber.user_id == User.id)
            .where(User.name.ilike(full_name))
            .where(PhoneNumber.verified.is_(True))
        )
        registered = {
            row.number: PhoneSuggestion(
                number=row.number,
                label=f"{row.number} — {row.name} ({row.email})",
            )
            for row in registered_result.all()
        }

    owner_stmt = select(distinct(Owner.phone_number))
    if owner_first_name:
        owner_stmt = owner_stmt.where(Owner.first_name.ilike(owner_first_name))
    if owner_last_name:
        owner_stmt = owner_stmt.where(Owner.last_name.ilike(owner_last_name))
    owner_result = await db.execute(owner_stmt)
    for (number,) in owner_result.all():
        if number not in registered:
            registered[number] = PhoneSuggestion(number=number, label=number)

    return list(registered.values())
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/discs.py backend/app/routers/users.py backend/app/routers/suggestions.py backend/app/repositories/disc.py
git commit -m "refactor(api): owner first/last fields, disc notes, split suggestions"
```

---

## Task 8: Backend test sweep — fix existing API/integration tests

**Files:**
- Modify: `backend/tests/test_discs.py`
- Modify: `backend/tests/test_suggestions.py`
- Modify: `backend/tests/test_users.py`
- Modify: `backend/tests/test_admin.py`

- [ ] **Step 1: Run the full backend suite to find failures**

Run: `cd backend && teststack run tests -- -x --tb=short`
Expected: failures concentrated in tests that POST `owner_name`/`phone_number` or assert on suggestions.

- [ ] **Step 2: Apply systematic substitutions across test files**

For every JSON payload field on disc create/update or wishlist:

| Old payload key | New payload keys |
|---|---|
| `"owner_name": "John Smith"` | `"owner_first_name": "John", "owner_last_name": "Smith"` |
| `"owner_name": "Cher"` | `"owner_first_name": "Cher", "owner_last_name": ""` |
| `"owner_name": None` (alongside `"phone_number": None`) | `"owner_first_name": None, "owner_last_name": None, "phone_number": None` |

For suggestion-list assertions:

| Old | New |
|---|---|
| `?field=owner_name` | use `?field=owner_first_name` and/or `?field=owner_last_name` |
| Phone suggestion `?owner_name=Foo` | `?owner_first_name=Foo&owner_last_name=` |

For `OwnerOut` assertions in JSON responses:
- `data["owner"]["name"]` — still works (computed field).
- New keys `data["owner"]["first_name"]` / `["last_name"]` are also present.

For disc response shape, `data["notes"]` is now `None` by default; tests that compared with `==` or did key-presence checks may need to assert `notes is None` or include it in expected dicts.

Walk every failing test, update the payload/expectation, re-run.

- [ ] **Step 3: Add a positive test for the wishlist notes round-trip**

Add to `backend/tests/test_users.py`:

```python
async def test_wishlist_disc_persists_notes(client, user_with_phone):
    headers, phone = user_with_phone
    resp = await client.post(
        "/me/wishlist",
        headers=headers,
        json={
            "manufacturer": "Innova",
            "name": "Destroyer",
            "color": "red",
            "phone_number": phone,
            "notes": "blue marker on rim",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["notes"] == "blue marker on rim"

    listing = await client.get("/me/wishlist", headers=headers)
    assert listing.status_code == 200
    [item] = listing.json()
    assert item["notes"] == "blue marker on rim"
```

(If the existing fixture is named differently — check `conftest.py` — adapt the fixture name and the way phone numbers are obtained. Use whatever fixture is already used by neighboring `/me/wishlist` tests in the file.)

- [ ] **Step 4: Add a positive test for `/me/discs` notes stripping**

Append to `backend/tests/test_users.py`:

```python
async def test_my_discs_strips_notes(client, admin_headers, user_with_phone):
    user_headers, phone = user_with_phone
    # Admin creates a found disc with notes for this owner.
    create = await client.post(
        "/discs",
        headers=admin_headers,
        json={
            "manufacturer": "Innova",
            "name": "Wraith",
            "color": "blue",
            "input_date": "2026-04-01",
            "owner_first_name": "Test",
            "owner_last_name": "User",
            "phone_number": phone,
            "notes": "admin-only note",
            "is_found": True,
        },
    )
    assert create.status_code == 201, create.text
    assert create.json()["notes"] == "admin-only note"

    mine = await client.get("/me/discs", headers=user_headers)
    assert mine.status_code == 200
    [disc] = mine.json()
    assert disc["notes"] is None
```

(Again, match fixture names to what already exists.)

- [ ] **Step 5: Add a unit test for owner_name filter on concatenated names**

Append to `backend/tests/test_discs.py`:

```python
async def test_owner_name_filter_matches_concatenated(client, admin_headers, db):
    from app.repositories.owner import OwnerRepository
    from app.repositories.disc import DiscRepository
    from datetime import date

    owner = await OwnerRepository(db).resolve_or_create(
        first_name="Alice", last_name="Walker", phone_number="+15550101010"
    )
    await DiscRepository(db).create(
        manufacturer="Innova", name="Roc", color="white",
        input_date=date(2026, 4, 1), owner_id=owner.id,
    )
    await db.commit()

    resp = await client.get("/discs?owner_name=Alice%20Walker", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(d["owner"]["first_name"] == "Alice" for d in items)
```

- [ ] **Step 6: Run the full suite green**

Run: `cd backend && teststack run tests -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/
git commit -m "test: update for owner first/last split and disc notes"
```

---

## Task 9: Regenerate frontend OpenAPI client

**Files:**
- Modify: `frontend/openapi.json`
- Modify: `frontend/src/api/northlanding.ts`

- [ ] **Step 1: Regenerate**

Run: `cd frontend && npm run generate:all`
Expected: schema and client updated. `git diff` should show the new field names.

- [ ] **Step 2: Quick sanity TypeScript check**

Run: `cd frontend && npm run build`
Expected: TypeScript errors in pages we haven't updated yet (`AdminDiscFormPage`, `MyWishlistPage`) — that's fine. Note the file:line of each error; subsequent tasks fix them.

- [ ] **Step 3: Commit**

```bash
git add frontend/openapi.json frontend/src/api/northlanding.ts
git commit -m "chore(frontend): regenerate API client for owner name split + notes"
```

---

## Task 10: Frontend `parseOwnerName` helper (TDD)

**Files:**
- Create: `frontend/src/utils/ownerName.ts`
- Create: `frontend/src/utils/ownerName.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/utils/ownerName.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { parseOwnerName } from './ownerName'

describe('parseOwnerName', () => {
  const cases: Array<[string, { first_name: string; last_name: string }]> = [
    ['Doe, John', { first_name: 'Doe', last_name: 'John' }],
    ['  Doe ,  John  ', { first_name: 'Doe', last_name: 'John' }],
    ['John Smith', { first_name: 'John', last_name: 'Smith' }],
    ['Mary Jane Watson', { first_name: 'Mary', last_name: 'Jane Watson' }],
    ['Cher', { first_name: 'Cher', last_name: '' }],
    ['', { first_name: '', last_name: '' }],
    ['   ', { first_name: '', last_name: '' }],
    ['a, b, c', { first_name: 'a', last_name: 'b, c' }],
  ]
  for (const [raw, expected] of cases) {
    it(`parses ${JSON.stringify(raw)}`, () => {
      expect(parseOwnerName(raw)).toEqual(expected)
    })
  }
})
```

- [ ] **Step 2: Run, expect failure**

Run: `cd frontend && npx vitest run src/utils/ownerName.test.ts`
Expected: FAIL — `ownerName.ts` not found.

- [ ] **Step 3: Implement**

Create `frontend/src/utils/ownerName.ts`:

```typescript
export function parseOwnerName(raw: string): {
  first_name: string
  last_name: string
} {
  const s = (raw ?? '').trim()
  if (!s) return { first_name: '', last_name: '' }
  const commaIdx = s.indexOf(',')
  if (commaIdx >= 0) {
    return {
      first_name: s.slice(0, commaIdx).trim(),
      last_name: s.slice(commaIdx + 1).trim(),
    }
  }
  const match = s.match(/^(\S+)\s+(.+)$/)
  if (!match) return { first_name: s, last_name: '' }
  return { first_name: match[1], last_name: match[2].trim() }
}
```

- [ ] **Step 4: Run, expect pass**

Run: `cd frontend && npx vitest run src/utils/ownerName.test.ts`
Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/ownerName.ts frontend/src/utils/ownerName.test.ts
git commit -m "feat(frontend): add parseOwnerName helper"
```

---

## Task 11: AdminDiscFormPage — split name inputs + notes

**Files:**
- Modify: `frontend/src/pages/AdminDiscFormPage.tsx`

- [ ] **Step 1: Update form state shape**

Replace the `DiscFormState` interface and `defaultForm`:

```typescript
interface DiscFormState {
  manufacturer: string
  name: string
  color: string
  input_date: string
  owner_first_name: string
  owner_last_name: string
  phone_number: string
  notes: string
  is_clear: boolean
  is_found: boolean
  is_returned: boolean
}

const defaultForm: DiscFormState = {
  manufacturer: '',
  name: '',
  color: '',
  input_date: new Date().toISOString().slice(0, 10),
  owner_first_name: '',
  owner_last_name: '',
  phone_number: '',
  notes: '',
  is_clear: false,
  is_found: true,
  is_returned: false,
}
```

- [ ] **Step 2: Update suggestion hooks**

Replace the two suggestion calls:

```typescript
const { data: ownerFirstNameSuggestions = [] } = useGetSuggestions(
  { field: 'owner_first_name' },
  { query: { retry: false } },
)
const { data: ownerLastNameSuggestions = [] } = useGetSuggestions(
  { field: 'owner_last_name' },
  { query: { retry: false } },
)
const { data: rawPhoneSuggestions = [] } = useGetPhoneSuggestions(
  {
    owner_first_name: form.owner_first_name,
    owner_last_name: form.owner_last_name,
  },
  { query: { enabled: !!form.owner_first_name || !!form.owner_last_name } },
)
```

(Delete `ownerNameSuggestions` and the old `owner_name` arg.)

- [ ] **Step 3: Update existing-disc hydration**

Replace the `useEffect` that initialises `form` from `existingDisc`:

```typescript
useEffect(() => {
  if (existingDisc) {
    setForm({
      manufacturer: existingDisc.manufacturer,
      name: existingDisc.name,
      color: existingDisc.color,
      input_date: existingDisc.input_date,
      owner_first_name: existingDisc.owner?.first_name ?? '',
      owner_last_name: existingDisc.owner?.last_name ?? '',
      phone_number: existingDisc.owner?.phone_number ?? '',
      notes: existingDisc.notes ?? '',
      is_clear: existingDisc.is_clear,
      is_found: existingDisc.is_found,
      is_returned: existingDisc.is_returned,
    })
  }
}, [existingDisc])
```

- [ ] **Step 4: Update name-change handler**

Replace `handleOwnerNameChange` with two:

```typescript
const handleOwnerFirstNameChange = (value: string) =>
  setForm((f) => ({ ...f, owner_first_name: value, phone_number: '' }))
const handleOwnerLastNameChange = (value: string) =>
  setForm((f) => ({ ...f, owner_last_name: value, phone_number: '' }))
```

- [ ] **Step 5: Update payload builder**

In `submitForm`, replace the `payload` block:

```typescript
const ownerSet = !!form.owner_first_name || !!form.owner_last_name || !!normalizedPhone
const payload = {
  manufacturer: form.manufacturer,
  name: form.name,
  color: form.color,
  input_date: form.input_date,
  is_clear: form.is_clear,
  is_found: form.is_found,
  is_returned: form.is_returned,
  notes: form.notes || null,
  owner_first_name: ownerSet ? form.owner_first_name : null,
  owner_last_name: ownerSet ? form.owner_last_name : null,
  phone_number: ownerSet ? normalizedPhone : null,
}
```

- [ ] **Step 6: Replace the owner UI block**

Replace the single "Owner name" `<div>` with two side-by-side fields, and add the Notes textarea after the checkboxes:

```tsx
<div className="grid grid-cols-2 gap-3">
  <div className="space-y-1.5">
    <Label htmlFor="disc-owner-first">First name</Label>
    <AutocompleteInput
      id="disc-owner-first"
      value={form.owner_first_name}
      suggestions={ownerFirstNameSuggestions.map((v) => ({ value: v }))}
      onValueChange={handleOwnerFirstNameChange}
      className={inputCls}
    />
  </div>
  <div className="space-y-1.5">
    <Label htmlFor="disc-owner-last">Last name</Label>
    <AutocompleteInput
      id="disc-owner-last"
      value={form.owner_last_name}
      suggestions={ownerLastNameSuggestions.map((v) => ({ value: v }))}
      onValueChange={handleOwnerLastNameChange}
      className={inputCls}
    />
  </div>
</div>
```

After the checkboxes block, add inside the same `<CardContent>`:

```tsx
<div className="space-y-1.5">
  <Label htmlFor="disc-notes">Notes</Label>
  <textarea
    id="disc-notes"
    rows={3}
    value={form.notes}
    onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
    className={`${inputCls} h-auto py-2`}
  />
</div>
```

- [ ] **Step 7: Type-check**

Run: `cd frontend && npm run build`
Expected: AdminDiscFormPage clean (other pages may still error — fixed in next tasks).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/AdminDiscFormPage.tsx
git commit -m "feat(admin): split owner name and add notes on disc form"
```

---

## Task 12: AdminDiscsPage — show notes; rely on computed `name`

**Files:**
- Modify: `frontend/src/pages/AdminDiscsPage.tsx`

- [ ] **Step 1: Show notes on the mobile card**

Inside the mobile card's `<div className="min-w-0 flex-1">` block, after the existing `phone_number` line, add:

```tsx
{disc.notes && (
  <p className="text-sm text-muted-foreground italic">{disc.notes}</p>
)}
```

- [ ] **Step 2: Show notes on the desktop table**

Add a column. In `<TableHeader>`, after `<TableHead>Owner</TableHead>`:

```tsx
<TableHead>Notes</TableHead>
```

In `<TableBody>` rows, after the Owner cell:

```tsx
<TableCell className="max-w-[16rem] truncate text-muted-foreground" title={disc.notes ?? ''}>
  {disc.notes ?? '—'}
</TableCell>
```

- [ ] **Step 3: Confirm `disc.owner.name` still resolves**

`OwnerOut.name` is the computed field — already in the regenerated TS types from Task 9. No code change needed; just sanity-check the build.

- [ ] **Step 4: Type-check**

Run: `cd frontend && npm run build`
Expected: AdminDiscsPage clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AdminDiscsPage.tsx
git commit -m "feat(admin): display disc notes column on disc list"
```

---

## Task 13: MyWishlistPage — notes input + send split owner name

**Files:**
- Modify: `frontend/src/pages/MyWishlistPage.tsx`

- [ ] **Step 1: Add the parser import and notes field to form state**

Top of file, alongside other imports:

```tsx
import { parseOwnerName } from '../utils/ownerName'
```

Replace the `useState` for `form`:

```tsx
const [form, setForm] = useState({ manufacturer: '', name: '', color: '', notes: '' })
```

- [ ] **Step 2: Update submit handler**

Replace `handleAdd`:

```tsx
const handleAdd = async (e: React.FormEvent) => {
  e.preventDefault()
  const { first_name, last_name } = parseOwnerName(user?.name ?? '')
  await addMutation.mutateAsync({
    data: {
      manufacturer: form.manufacturer,
      name: form.name,
      color: form.color,
      phone_number: phoneNumber,
      owner_first_name: first_name,
      owner_last_name: last_name,
      notes: form.notes || null,
    },
  })
  queryClient.invalidateQueries({ queryKey: getGetMyWishlistQueryKey() })
  setForm({ manufacturer: '', name: '', color: '', notes: '' })
}
```

- [ ] **Step 3: Add the notes input to the form UI**

Inside the existing `<form>` between the color autocomplete and the phone block, add:

```tsx
<input
  type="text"
  placeholder="Notes (optional)"
  value={form.notes}
  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
  className={`${inputCls} flex-1 min-w-32`}
/>
```

- [ ] **Step 4: Display notes on each wishlist row**

Inside the wishlist `<li>` `<span>` block, after the color span, add:

```tsx
{disc.notes && (
  <span className="ml-2 text-sm text-muted-foreground italic">· {disc.notes}</span>
)}
```

- [ ] **Step 5: Type-check + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/MyWishlistPage.tsx
git commit -m "feat(wishlist): notes input and split-name submission"
```

---

## Task 14: Import script — comma-aware parsing

**Files:**
- Modify: `scripts/import_discs.py`

- [ ] **Step 1: Add an inline parser**

Below the imports, add (script does not depend on backend modules — it's HTTP-only):

```python
def parse_owner_name(raw: str | None) -> tuple[str, str]:
    if raw is None:
        return ("", "")
    s = raw.strip()
    if not s:
        return ("", "")
    if "," in s:
        first, _, last = s.partition(",")
        return (first.strip(), last.strip())
    parts = s.split(None, 1)
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[1].strip())
```

- [ ] **Step 2: Update `ParsedRow`**

Replace the dataclass:

```python
@dataclass
class ParsedRow:
    first_name: str | None
    last_name: str | None
    phone: str | None
    manufacturer: str
    model: str
    color: str
    date_found: date
    date_found_missing: bool
    date_returned: date | None
    is_clear: bool
```

- [ ] **Step 3: Update `parse_row`**

Replace the function body:

```python
def parse_row(row: tuple) -> ParsedRow | None:
    name = _clean(row[0])
    phone_raw = _clean(row[1])
    manufacturer = _clean(row[2])
    model = _clean(row[3])
    color = _clean(row[4])
    date_found = _to_date(row[7])
    date_returned = _to_date(row[8])

    if not any((name, phone_raw, manufacturer, model, color, date_found, date_returned)):
        return None

    color_lower = (color or "").lower()
    is_clear = any(token in color_lower for token in ("clear", "trans", "tint"))

    if _is_real_name(name):
        first, last = parse_owner_name(name)
    else:
        first, last = None, None

    return ParsedRow(
        first_name=first,
        last_name=last,
        phone=_try_phone(phone_raw),
        manufacturer=manufacturer or "",
        model=model or "",
        color=color or "",
        date_found=date_found or date.today(),
        date_found_missing=date_found is None,
        date_returned=date_returned,
        is_clear=is_clear,
    )
```

- [ ] **Step 4: Update `build_create_payload`**

```python
def build_create_payload(parsed: ParsedRow) -> dict:
    payload = {
        "manufacturer": parsed.manufacturer,
        "name": parsed.model,
        "color": parsed.color,
        "input_date": parsed.date_found.isoformat(),
        "is_clear": parsed.is_clear,
        "is_found": True,
    }
    if parsed.first_name is not None and parsed.last_name is not None and parsed.phone:
        payload["owner_first_name"] = parsed.first_name
        payload["owner_last_name"] = parsed.last_name
        payload["phone_number"] = parsed.phone
    return payload
```

- [ ] **Step 5: Update `import_sheet` owner-presence check**

Find the line `has_owner = "owner_name" in payload` and replace with:

```python
has_owner = "owner_first_name" in payload
```

- [ ] **Step 6: Update the docstring**

In the module docstring's `Behavior:` section, replace the bullet about Name parsing:

```text
    * Owner is sent only when Name is a real name AND Phone normalizes to a US
      10-digit number. Names containing a comma are split as "first, last"
      (first name in front of the comma); otherwise on the first whitespace
      run, with single tokens producing an empty last name. Otherwise the disc
      is created ownerless.
```

- [ ] **Step 7: Smoke-test with `--dry-run` against a fixture xlsx**

If you have a sample spreadsheet, run:

```bash
cd /Users/daniel/conductor/workspaces/northlandingdiscreturn/san-jose-v1
uv run --project backend python scripts/import_discs.py path/to/sample.xlsx --dry-run --limit 5
```

Expected: parses without error and reports owner counts. If no fixture is available, this step is best-effort — the unit-style behavior is covered manually by reading the diff.

- [ ] **Step 8: Commit**

```bash
git add scripts/import_discs.py
git commit -m "feat(scripts): import_discs sends split owner name fields"
```

---

## Task 15: Final verification

- [ ] **Step 1: Backend full suite**

Run: `cd backend && teststack run tests -v`
Expected: all PASS.

- [ ] **Step 2: Frontend build + lint + tests**

Run: `cd frontend && npm run build && npm run lint && npx vitest run`
Expected: all PASS.

- [ ] **Step 3: Manual smoke (UI)**

Start the stack (`docker compose up`) and:
- Open the admin add-disc page; confirm two name fields and notes textarea render.
- Save a disc with `Doe / John / +15551234567`; confirm it appears in the list with `Doe John` and the note shown.
- Open `/me/wishlist` as a non-admin; add a wishlist entry with notes; confirm note shows on the list.
- Open `/me/discs` (any user with a found disc) and confirm notes are not visible.
- (Sanity) Edit an existing imported disc and confirm hydration of split name + notes works.

If you cannot run the UI in this session, state so explicitly and skip this step rather than claim success.

- [ ] **Step 4: Final commit if any leftover snapshot/lock changes**

```bash
git status
# only if there are stragglers (lock files, snapshot updates):
git add -p
git commit -m "chore: misc snapshot updates"
```

---

## Self-Review

- **Spec coverage:**
  - § Data Model → Tasks 2, 3.
  - § Migration → Task 3.
  - § Owner Name Parsing Helper (backend) → Task 1.
  - § Owner Resolution (no DB uniqueness, app-level dedup) → Task 4.
  - § Heads-Up SMS (unchanged) → no task; verified by existing tests in Task 8.
  - § API Surface (OwnerOut, DiscCreate/Update, DiscOut, WishlistDiscCreate, suggestions) → Tasks 5, 7.
  - § Frontend admin form → Task 11.
  - § Frontend admin list → Task 12.
  - § Frontend wishlist (notes input, parseOwnerName) → Tasks 10, 13.
  - § Frontend MyDiscs (no notes) → ensured server-side in Task 7 step 4; verified Task 8 step 4.
  - § Import script → Task 14.
  - § Testing (parser unit, migration smoke, API, frontend, import script) → Tasks 1, 3, 8, 10, 14, 15.

- **Placeholder scan:** No "TBD"/"TODO". Test fixture names in Task 8 step 3-4 are flagged as needing local adaptation, with concrete instructions to mirror neighboring tests.

- **Type consistency:** `parse_owner_name` returns `tuple[str, str]` (Python) and `{ first_name, last_name }` (TS) — consistent. `OwnerOut.name` is computed from `first_name + " " + last_name` in three places (model, schema, frontend display) — consistent. `OwnerRepository.resolve_or_create` keyword args (`first_name`, `last_name`, `phone_number`) match the call sites in routers and tests.
