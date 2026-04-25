# Owner / User Separation Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract disc ownership from freetext columns on `discs` into a dedicated `owners` table keyed by `(name, phone_number)`, and send a one-time heads-up SMS the first time a disc is logged for a new owner.

**Architecture:** New `owners` table, `discs.owner_id` nullable FK replacing `owner_name`/`phone_number`. Admin disc creation resolves-or-creates an Owner and — for found discs to brand-new owners — enqueues a heads-up SMSJob and stamps `owner.heads_up_sent_at`. User→disc lookup traverses `user's verified phones → owners.phone_number → discs`.

**Tech Stack:** FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2, pytest + pytest-asyncio, React/TypeScript frontend.

**Spec:** `docs/superpowers/specs/2026-04-24-owner-refactor-design.md`

---

## File Map

- Create: `backend/app/models/owner.py`
- Create: `backend/app/repositories/owner.py`
- Create: `backend/app/schemas/owner.py`
- Create: `backend/alembic/versions/<new>_owners_table.py`
- Create: `backend/tests/test_owners.py`
- Modify: `backend/app/models/disc.py` (drop old cols, add FK + relationship)
- Modify: `backend/app/schemas/disc.py` (DiscOut nests OwnerOut; Create/Update keep name+phone)
- Modify: `backend/app/repositories/disc.py` (owner_id path; drop phone-based queries)
- Modify: `backend/app/routers/discs.py` (resolve-or-create + heads-up on create)
- Modify: `backend/app/routers/users.py` (wishlist owner resolution; /me/discs by owner)
- Modify: `backend/app/routers/suggestions.py` (source from owners table)
- Modify: `backend/app/services/notification.py` (group by owner_id)
- Modify: `backend/tests/test_discs.py`, `test_users.py`, `test_suggestions.py`, `test_admin.py` (fixture updates)
- Modify: `frontend/src/pages/AdminDiscFormPage.tsx` and generated API types (no behavior change; DiscOut shape)

---

## Conventions

- All write endpoints call `await db.commit()` in the router; repositories only `flush()`.
- Tests use `pytest-asyncio` auto mode, the `db` and `client` fixtures from `backend/tests/conftest.py`, and the inline `admin_headers()` / `make_admin()` helpers established in `backend/tests/test_discs.py`.
- Run tests from the `backend/` directory: `cd backend && pytest <path>`.
- Commit after every green-test step.

---

## Task 1: Add `Owner` model

**Files:**
- Create: `backend/app/models/owner.py`
- Modify: `backend/app/models/__init__.py` (if it exists — otherwise skip)
- Test: `backend/tests/test_owners.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_owners.py`:

```python
import uuid
from app.models.owner import Owner


async def test_owner_model_persists(db):
    owner = Owner(name="John Smith", phone_number="+15551234567")
    db.add(owner)
    await db.flush()
    await db.refresh(owner)
    assert isinstance(owner.id, uuid.UUID)
    assert owner.name == "John Smith"
    assert owner.phone_number == "+15551234567"
    assert owner.heads_up_sent_at is None
    assert owner.created_at is not None


async def test_owner_unique_name_phone(db):
    from sqlalchemy.exc import IntegrityError
    db.add(Owner(name="Jane", phone_number="+15550001111"))
    await db.flush()
    db.add(Owner(name="Jane", phone_number="+15550001111"))
    try:
        await db.flush()
        assert False, "should have raised IntegrityError"
    except IntegrityError:
        await db.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_owners.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.owner'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/owner.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class Owner(Base):
    __tablename__ = "owners"
    __table_args__ = (
        UniqueConstraint("name", "phone_number", name="uq_owners_name_phone"),
        Index("ix_owners_phone_number", "phone_number"),
        Index("ix_owners_name", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_owners.py -v`

Expected: PASS both tests. (If a forward-ref error occurs on `Disc`, temporarily change the relationship to `discs: Mapped[list] = relationship(back_populates="owner")` — it will be fully resolved in Task 3.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/owner.py backend/tests/test_owners.py
git commit -m "feat(owner): add Owner model"
```

---

## Task 2: Alembic migration — add `owners` table and `discs.owner_id`

**Files:**
- Create: `backend/alembic/versions/<rev>_owners_table.py`

- [ ] **Step 1: Generate a migration skeleton**

Run: `cd backend && alembic revision -m "owners table and discs.owner_id"`

This creates a new file in `backend/alembic/versions/`. Open it and replace its body with the content below. Keep the auto-generated `revision` and `down_revision` values — do NOT copy placeholders.

- [ ] **Step 2: Write the migration**

Replace the body of the new migration file with:

```python
"""owners table and discs.owner_id

Revision ID: <leave as generated>
Revises: 5846ff30f7c2
Create Date: <leave as generated>

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# NOTE: revision / down_revision / branch_labels / depends_on lines
# are generated by `alembic revision` — do not duplicate them here.


def upgrade() -> None:
    # 1. Create owners table
    op.create_table(
        "owners",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column("heads_up_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", "phone_number", name="uq_owners_name_phone"),
    )
    op.create_index("ix_owners_phone_number", "owners", ["phone_number"])
    op.create_index("ix_owners_name", "owners", ["name"])

    # 2. Add discs.owner_id
    op.add_column(
        "discs",
        sa.Column("owner_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_discs_owner_id",
        "discs",
        "owners",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_discs_owner_id", "discs", ["owner_id"])

    # 3. Backfill owners from existing discs (one row per distinct
    #    non-null (owner_name, phone_number) pair). heads_up_sent_at is
    #    set to the earliest disc.created_at for that pair, so existing
    #    owners are treated as already contacted.
    op.execute(
        """
        INSERT INTO owners (id, name, phone_number, heads_up_sent_at, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            owner_name,
            phone_number,
            MIN(created_at),
            MIN(created_at),
            NOW()
        FROM discs
        WHERE owner_name IS NOT NULL
          AND phone_number IS NOT NULL
        GROUP BY owner_name, phone_number
        """
    )

    # 4. Link discs to their owner row
    op.execute(
        """
        UPDATE discs
        SET owner_id = owners.id
        FROM owners
        WHERE discs.owner_name = owners.name
          AND discs.phone_number = owners.phone_number
        """
    )

    # 5. Drop the old freetext columns
    op.drop_column("discs", "owner_name")
    op.drop_column("discs", "phone_number")


def downgrade() -> None:
    op.add_column("discs", sa.Column("owner_name", sa.String(), nullable=True))
    op.add_column("discs", sa.Column("phone_number", sa.String(), nullable=True))

    op.execute(
        """
        UPDATE discs
        SET owner_name = owners.name,
            phone_number = owners.phone_number
        FROM owners
        WHERE discs.owner_id = owners.id
        """
    )

    op.drop_index("ix_discs_owner_id", table_name="discs")
    op.drop_constraint("fk_discs_owner_id", "discs", type_="foreignkey")
    op.drop_column("discs", "owner_id")
    op.drop_index("ix_owners_name", table_name="owners")
    op.drop_index("ix_owners_phone_number", table_name="owners")
    op.drop_table("owners")
```

`gen_random_uuid()` requires the `pgcrypto` extension (already enabled by PostgreSQL 13+ by default on Autodesk's managed Postgres; if an error says otherwise, prepend `op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')`).

- [ ] **Step 3: Verify the migration applies cleanly**

Run: `cd backend && alembic upgrade head`

Expected: migration runs without error. Then:

Run: `cd backend && alembic downgrade -1 && alembic upgrade head`

Expected: down-then-up round trip succeeds.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(owner): migration for owners table and discs.owner_id"
```

---

## Task 3: Update `Disc` model

**Files:**
- Modify: `backend/app/models/disc.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_owners.py`:

```python
from datetime import date
from app.models.disc import Disc


async def test_disc_has_owner_relationship(db):
    owner = Owner(name="Ada", phone_number="+15559990000")
    db.add(owner)
    await db.flush()
    disc = Disc(
        manufacturer="Innova",
        name="Destroyer",
        color="red",
        input_date=date(2026, 4, 1),
        owner_id=owner.id,
    )
    db.add(disc)
    await db.flush()
    await db.refresh(disc)
    assert disc.owner_id == owner.id
    assert disc.owner.name == "Ada"


async def test_disc_owner_id_nullable(db):
    disc = Disc(
        manufacturer="Innova",
        name="Wraith",
        color="blue",
        input_date=date(2026, 4, 1),
    )
    db.add(disc)
    await db.flush()
    await db.refresh(disc)
    assert disc.owner_id is None
```

- [ ] **Step 2: Run tests to see them fail**

Run: `cd backend && pytest tests/test_owners.py -v`

Expected: FAIL (model still has `owner_name`/`phone_number`, no `owner_id`).

- [ ] **Step 3: Replace `backend/app/models/disc.py`**

```python
import uuid
from datetime import datetime, date
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class Disc(Base):
    __tablename__ = "discs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manufacturer: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_clear: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    input_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_found: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_returned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    final_notice_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["Owner | None"] = relationship(back_populates="discs")
    photos: Mapped[list["DiscPhoto"]] = relationship(
        back_populates="disc",
        cascade="all, delete-orphan",
        order_by="DiscPhoto.sort_order",
    )
    pickup_notifications: Mapped[list["DiscPickupNotification"]] = relationship(
        back_populates="disc"
    )


class DiscPhoto(Base):
    __tablename__ = "disc_photos"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    disc_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("discs.id"), nullable=False)
    photo_path: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    disc: Mapped["Disc"] = relationship(back_populates="photos")
```

Also ensure `from app.models.owner import Owner` is imported somewhere that gets loaded on app startup (e.g., add it to `backend/app/models/__init__.py` if one exists — otherwise import it in `backend/app/main.py` alongside other models). Check what the existing codebase does by looking at how `User` and `PickupEvent` are imported, and follow the same pattern.

- [ ] **Step 4: Run all tests in test_owners.py**

Run: `cd backend && pytest tests/test_owners.py -v`

Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/disc.py backend/app/models/ backend/tests/test_owners.py
git commit -m "feat(owner): discs.owner_id FK replaces owner_name/phone_number"
```

---

## Task 4: `OwnerRepository` with resolve-or-create

**Files:**
- Create: `backend/app/repositories/owner.py`
- Test: `backend/tests/test_owners.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_owners.py`:

```python
from app.repositories.owner import OwnerRepository


async def test_repo_resolve_creates_new_owner(db):
    repo = OwnerRepository(db)
    owner = await repo.resolve_or_create(name="Jill", phone_number="+15551111111")
    assert owner.id is not None
    assert owner.heads_up_sent_at is None
    await db.commit()


async def test_repo_resolve_returns_existing_owner(db):
    repo = OwnerRepository(db)
    first = await repo.resolve_or_create(name="Jack", phone_number="+15552222222")
    await db.commit()
    second = await repo.resolve_or_create(name="Jack", phone_number="+15552222222")
    assert first.id == second.id


async def test_repo_get_by_phones(db):
    repo = OwnerRepository(db)
    a = await repo.resolve_or_create(name="A", phone_number="+15553333333")
    b = await repo.resolve_or_create(name="B", phone_number="+15553333333")
    await repo.resolve_or_create(name="C", phone_number="+15559999999")
    await db.commit()
    owners = await repo.list_by_phones(["+15553333333"])
    assert {o.id for o in owners} == {a.id, b.id}


async def test_repo_mark_heads_up_sent(db):
    repo = OwnerRepository(db)
    owner = await repo.resolve_or_create(name="D", phone_number="+15554444444")
    await db.commit()
    assert owner.heads_up_sent_at is None
    await repo.mark_heads_up_sent(owner)
    await db.commit()
    await db.refresh(owner)
    assert owner.heads_up_sent_at is not None
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `cd backend && pytest tests/test_owners.py::test_repo_resolve_creates_new_owner -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.repositories.owner'`.

- [ ] **Step 3: Create the repository**

Create `backend/app/repositories/owner.py`:

```python
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.owner import Owner


class OwnerRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_or_create(self, *, name: str, phone_number: str) -> Owner:
        result = await self.db.execute(
            select(Owner).where(
                Owner.name == name,
                Owner.phone_number == phone_number,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        owner = Owner(name=name, phone_number=phone_number)
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

    async def suggest_names(self, limit: int = 50) -> list[str]:
        result = await self.db.execute(
            select(Owner.name).distinct().order_by(func.lower(Owner.name)).limit(limit)
        )
        return [row[0] for row in result.all()]

    async def list_phones_for_name(self, name: str) -> list[str]:
        result = await self.db.execute(
            select(Owner.phone_number).where(Owner.name.ilike(name)).distinct()
        )
        return [row[0] for row in result.all()]
```

- [ ] **Step 4: Run repository tests**

Run: `cd backend && pytest tests/test_owners.py -v`

Expected: PASS all.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/owner.py backend/tests/test_owners.py
git commit -m "feat(owner): OwnerRepository with resolve_or_create"
```

---

## Task 5: `OwnerOut` schema and update `DiscOut`

**Files:**
- Create: `backend/app/schemas/owner.py`
- Modify: `backend/app/schemas/disc.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_owners.py`:

```python
from app.schemas.disc import DiscOut


async def test_disc_out_embeds_owner(db):
    from app.repositories.owner import OwnerRepository
    from app.repositories.disc import DiscRepository
    from datetime import date
    owner = await OwnerRepository(db).resolve_or_create(
        name="Eva", phone_number="+15555555555"
    )
    disc = await DiscRepository(db).create(
        manufacturer="MVP", name="Wave", color="green",
        input_date=date(2026, 4, 1), owner_id=owner.id,
    )
    await db.commit()
    out = DiscOut.model_validate(disc)
    assert out.owner is not None
    assert out.owner.name == "Eva"
    assert out.owner.phone_number == "+15555555555"
```

This test uses `DiscRepository.create(owner_id=...)`, which doesn't exist yet — that's Task 6. Run it to see two failures (schema + repo). Fix both together by completing Task 5 and Task 6 in sequence without committing between them if convenient, OR skip this test's `DiscRepository.create` call by directly constructing `Disc(owner_id=owner.id, ...)` and adding to `db` — pick whichever is less friction.

- [ ] **Step 2: Create `backend/app/schemas/owner.py`**

```python
import uuid
from datetime import datetime
from pydantic import BaseModel


class OwnerOut(BaseModel):
    id: uuid.UUID
    name: str
    phone_number: str
    heads_up_sent_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Replace `backend/app/schemas/disc.py`**

```python
# backend/app/schemas/disc.py
import uuid
from datetime import datetime, date
from pydantic import BaseModel, field_validator
from app.phone import normalize_phone
from app.schemas.owner import OwnerOut
from app.services.storage import storage_path_to_url
from pydantic import model_validator


class DiscPhotoOut(BaseModel):
    id: uuid.UUID
    photo_path: str
    sort_order: int

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def normalize_photo_path(self) -> "DiscPhotoOut":
        self.photo_path = storage_path_to_url(self.photo_path)
        return self


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
    photos: list[DiscPhotoOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscCreate(BaseModel):
    manufacturer: str
    name: str
    color: str
    input_date: date
    owner_name: str | None = None
    phone_number: str | None = None
    is_clear: bool = False
    is_found: bool = True

    @field_validator("phone_number")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        return normalize_phone(v) if v else None

    @model_validator(mode="after")
    def owner_fields_together(self) -> "DiscCreate":
        # Allow neither-or-both. A lone name or lone phone is ambiguous.
        if (self.owner_name is None) != (self.phone_number is None):
            raise ValueError(
                "owner_name and phone_number must be provided together or not at all"
            )
        return self


class DiscUpdate(BaseModel):
    manufacturer: str | None = None
    name: str | None = None
    color: str | None = None
    owner_name: str | None = None
    phone_number: str | None = None
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
    owner_name: str | None = None

    @field_validator("phone_number")
    @classmethod
    def normalize(cls, v: str) -> str:
        return normalize_phone(v)


class DiscPage(BaseModel):
    items: list[DiscOut]
    page: int
    page_size: int
    total: int
```

- [ ] **Step 4: Run schema tests**

Run: `cd backend && pytest tests/test_owners.py::test_disc_out_embeds_owner -v`

Expected: PASS after Task 6 lands (if it fails now because `DiscRepository.create` doesn't accept `owner_id`, either proceed to Task 6 first or simplify the test as described above).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/owner.py backend/app/schemas/disc.py backend/tests/test_owners.py
git commit -m "feat(owner): OwnerOut schema; DiscOut embeds owner"
```

---

## Task 6: Update `DiscRepository` for `owner_id`

**Files:**
- Modify: `backend/app/repositories/disc.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_owners.py`:

```python
async def test_disc_repo_create_with_owner_id(db):
    from app.repositories.owner import OwnerRepository
    from app.repositories.disc import DiscRepository
    from datetime import date
    owner = await OwnerRepository(db).resolve_or_create(
        name="Fred", phone_number="+15556666666"
    )
    disc = await DiscRepository(db).create(
        manufacturer="Discraft", name="Buzzz", color="yellow",
        input_date=date(2026, 4, 1), owner_id=owner.id,
    )
    await db.commit()
    assert disc.owner_id == owner.id


async def test_disc_repo_list_by_owner_ids(db):
    from app.repositories.owner import OwnerRepository
    from app.repositories.disc import DiscRepository
    from datetime import date
    repo = DiscRepository(db)
    o1 = await OwnerRepository(db).resolve_or_create(name="G", phone_number="+15557000001")
    o2 = await OwnerRepository(db).resolve_or_create(name="H", phone_number="+15557000002")
    d1 = await repo.create(manufacturer="m", name="n", color="c",
                           input_date=date(2026,4,1), owner_id=o1.id)
    d2 = await repo.create(manufacturer="m", name="n", color="c",
                           input_date=date(2026,4,1), owner_id=o2.id, is_found=False)
    await db.commit()
    found = await repo.list_found_by_owner_ids([o1.id, o2.id])
    wish = await repo.list_wishlist_by_owner_ids([o1.id, o2.id])
    assert {d.id for d in found} == {d1.id}
    assert {d.id for d in wish} == {d2.id}
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd backend && pytest tests/test_owners.py -v`

Expected: multiple FAILs referencing `owner_id` arg or missing methods.

- [ ] **Step 3: Replace `backend/app/repositories/disc.py`**

```python
# backend/app/repositories/disc.py
import uuid
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.disc import Disc, DiscPhoto


class DiscRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

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
    ) -> Disc:
        disc = Disc(
            manufacturer=manufacturer,
            name=name,
            color=color,
            input_date=input_date,
            owner_id=owner_id,
            is_clear=is_clear,
            is_found=is_found,
        )
        self.db.add(disc)
        await self.db.flush()
        await self.db.refresh(disc)
        return disc

    async def get_by_id(self, disc_id: uuid.UUID) -> Disc | None:
        result = await self.db.execute(
            select(Disc)
            .where(Disc.id == disc_id)
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        is_found: bool | None = None,
        is_returned: bool | None = None,
        owner_name: str | None = None,
    ) -> list[Disc]:
        from app.models.owner import Owner
        offset = (page - 1) * page_size
        stmt = (
            select(Disc)
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
            .order_by(Disc.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        if is_found is not None:
            stmt = stmt.where(Disc.is_found == is_found)
        if is_returned is not None:
            stmt = stmt.where(Disc.is_returned == is_returned)
        if owner_name is not None:
            stmt = stmt.join(Owner, Disc.owner_id == Owner.id).where(
                Owner.name.ilike(f"%{owner_name}%")
            )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_owner_ids(self, owner_ids: list[uuid.UUID]) -> list[Disc]:
        if not owner_ids:
            return []
        result = await self.db.execute(
            select(Disc)
            .where(Disc.owner_id.in_(owner_ids), Disc.is_found == True)  # noqa: E712
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
            .order_by(Disc.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_found_by_owner_ids(self, owner_ids: list[uuid.UUID]) -> list[Disc]:
        return await self.list_by_owner_ids(owner_ids)

    async def list_wishlist_by_owner_ids(self, owner_ids: list[uuid.UUID]) -> list[Disc]:
        if not owner_ids:
            return []
        result = await self.db.execute(
            select(Disc)
            .where(Disc.owner_id.in_(owner_ids), Disc.is_found == False)  # noqa: E712
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
            .order_by(Disc.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_all(
        self,
        *,
        is_found: bool | None = None,
        is_returned: bool | None = None,
        owner_name: str | None = None,
    ) -> int:
        from app.models.owner import Owner
        stmt = select(func.count()).select_from(Disc)
        if owner_name is not None:
            stmt = stmt.join(Owner, Disc.owner_id == Owner.id).where(
                Owner.name.ilike(f"%{owner_name}%")
            )
        if is_found is not None:
            stmt = stmt.where(Disc.is_found == is_found)
        if is_returned is not None:
            stmt = stmt.where(Disc.is_returned == is_returned)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def count_by_owner_ids(self, owner_ids: list[uuid.UUID]) -> int:
        if not owner_ids:
            return 0
        result = await self.db.execute(
            select(func.count()).select_from(Disc).where(
                Disc.owner_id.in_(owner_ids),
                Disc.is_found == True,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def list_unreturned_found(self) -> list[Disc]:
        result = await self.db.execute(
            select(Disc)
            .where(
                Disc.is_found == True,  # noqa: E712
                Disc.is_returned == False,  # noqa: E712
                Disc.owner_id.isnot(None),
            )
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
        )
        return list(result.scalars().all())

    async def update(self, disc: Disc, **kwargs) -> Disc:
        for key, value in kwargs.items():
            setattr(disc, key, value)
        await self.db.flush()
        await self.db.refresh(disc)
        return disc

    async def delete(self, disc_id: uuid.UUID) -> None:
        result = await self.db.execute(select(Disc).where(Disc.id == disc_id))
        disc = result.scalar_one_or_none()
        if disc:
            await self.db.delete(disc)
            await self.db.flush()

    async def add_photo(self, disc_id: uuid.UUID, photo_path: str, sort_order: int = 0) -> DiscPhoto:
        photo = DiscPhoto(disc_id=disc_id, photo_path=photo_path, sort_order=sort_order)
        self.db.add(photo)
        await self.db.flush()
        await self.db.refresh(photo)
        return photo

    async def delete_photo(self, photo_id: uuid.UUID) -> str | None:
        result = await self.db.execute(select(DiscPhoto).where(DiscPhoto.id == photo_id))
        photo = result.scalar_one_or_none()
        if photo:
            path = photo.photo_path
            await self.db.delete(photo)
            await self.db.flush()
            return path
        return None
```

Removed: `list_by_phone`, `list_by_phones`, `list_wishlist_by_phones`, `list_found_by_phones`, `count_by_phones`. Replace callers as noted in Tasks 7–10.

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_owners.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/disc.py backend/tests/test_owners.py
git commit -m "refactor(owner): DiscRepository uses owner_id"
```

---

## Task 7: Heads-up SMS helper + admin create flow

**Files:**
- Create: `backend/app/services/heads_up.py`
- Modify: `backend/app/routers/discs.py`
- Test: `backend/tests/test_owners.py` and `backend/tests/test_discs.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_owners.py`:

```python
from sqlalchemy import select
from app.models.pickup_event import SMSJob


async def test_heads_up_enqueued_on_first_found_disc(db):
    from app.services.heads_up import maybe_enqueue_heads_up
    from app.repositories.owner import OwnerRepository

    owner = await OwnerRepository(db).resolve_or_create(
        name="Iris", phone_number="+15558000001"
    )
    await db.commit()

    sent = await maybe_enqueue_heads_up(owner=owner, is_found=True, db=db)
    await db.commit()
    assert sent is True
    await db.refresh(owner)
    assert owner.heads_up_sent_at is not None

    jobs = (await db.execute(select(SMSJob).where(SMSJob.phone_number == owner.phone_number))).scalars().all()
    assert len(jobs) == 1
    assert "North Landing Disc Return" in jobs[0].message


async def test_heads_up_not_re_enqueued(db):
    from app.services.heads_up import maybe_enqueue_heads_up
    from app.repositories.owner import OwnerRepository
    owner = await OwnerRepository(db).resolve_or_create(
        name="Jay", phone_number="+15558000002"
    )
    await db.commit()
    await maybe_enqueue_heads_up(owner=owner, is_found=True, db=db)
    await db.commit()
    sent_again = await maybe_enqueue_heads_up(owner=owner, is_found=True, db=db)
    await db.commit()
    assert sent_again is False
    jobs = (await db.execute(select(SMSJob).where(SMSJob.phone_number == owner.phone_number))).scalars().all()
    assert len(jobs) == 1


async def test_heads_up_not_enqueued_for_wishlist(db):
    from app.services.heads_up import maybe_enqueue_heads_up
    from app.repositories.owner import OwnerRepository
    owner = await OwnerRepository(db).resolve_or_create(
        name="Kay", phone_number="+15558000003"
    )
    await db.commit()
    sent = await maybe_enqueue_heads_up(owner=owner, is_found=False, db=db)
    await db.commit()
    assert sent is False
    await db.refresh(owner)
    assert owner.heads_up_sent_at is None
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd backend && pytest tests/test_owners.py -v`

Expected: FAIL — `app.services.heads_up` not found.

- [ ] **Step 3: Create `backend/app/services/heads_up.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.owner import Owner
from app.repositories.owner import OwnerRepository
from app.repositories.pickup_event import PickupEventRepository


HEADS_UP_TEMPLATE = (
    "Hi {name}, this is North Landing Disc Return. We found one of your discs. "
    "We'll text you again when we schedule a pickup event — these happen every "
    "1-2 months. Reply STOP to opt out."
)


async def maybe_enqueue_heads_up(
    *, owner: Owner, is_found: bool, db: AsyncSession
) -> bool:
    """Enqueue the one-time intro SMS to this owner. Returns True if enqueued."""
    if not is_found:
        return False
    if owner.heads_up_sent_at is not None:
        return False
    message = HEADS_UP_TEMPLATE.format(name=owner.name)
    await PickupEventRepository(db).create_sms_job(
        phone_number=owner.phone_number, message=message
    )
    await OwnerRepository(db).mark_heads_up_sent(owner)
    return True
```

- [ ] **Step 4: Run heads-up tests**

Run: `cd backend && pytest tests/test_owners.py -v`

Expected: PASS the three new tests.

- [ ] **Step 5: Update `backend/app/routers/discs.py` create_disc and update_disc**

Read the current file. In `create_disc`, replace the `repo.create(**body.model_dump())` line with the resolve-or-create flow. In `update_disc`, when `owner_name` or `phone_number` changes, re-resolve. Full handler bodies:

```python
# create_disc
@router.post("", response_model=DiscOut, status_code=201, operation_id="createDisc")
async def create_disc(
    body: DiscCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Disc:
    repo = DiscRepository(db)
    owner_id = None
    owner_obj = None
    if body.owner_name and body.phone_number:
        owner_obj = await OwnerRepository(db).resolve_or_create(
            name=body.owner_name, phone_number=body.phone_number
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
    )

    if owner_obj is not None:
        await maybe_enqueue_heads_up(owner=owner_obj, is_found=disc.is_found, db=db)

    await db.commit()
    # Reload with owner + photos for the response
    return await repo.get_by_id(disc.id)


# update_disc
@router.patch("/{disc_id}", response_model=DiscOut, operation_id="updateDisc")
async def update_disc(
    disc_id: uuid.UUID,
    body: DiscUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Disc:
    repo = DiscRepository(db)
    disc = await repo.get_by_id(disc_id)
    if disc is None:
        raise HTTPException(status_code=404, detail="Disc not found")

    payload = body.model_dump(exclude_unset=True)
    owner_name = payload.pop("owner_name", None)
    phone_number = payload.pop("phone_number", None)

    # Re-resolve owner if either field is present in the request
    if "owner_name" in body.model_fields_set or "phone_number" in body.model_fields_set:
        effective_name = owner_name if "owner_name" in body.model_fields_set else (
            disc.owner.name if disc.owner else None
        )
        effective_phone = phone_number if "phone_number" in body.model_fields_set else (
            disc.owner.phone_number if disc.owner else None
        )
        if effective_name and effective_phone:
            new_owner = await OwnerRepository(db).resolve_or_create(
                name=effective_name, phone_number=effective_phone
            )
            payload["owner_id"] = new_owner.id
        else:
            payload["owner_id"] = None

    await repo.update(disc, **payload)
    await db.commit()
    return await repo.get_by_id(disc_id)
```

Add the import at the top of the file:

```python
from app.repositories.owner import OwnerRepository
from app.services.heads_up import maybe_enqueue_heads_up
```

- [ ] **Step 6: Update the admin list filter**

In `list_discs`, the non-admin branch currently does `user_repo.get_verified_numbers()` → `repo.list_by_phones(numbers)`. Change it to:

```python
numbers = await user_repo.get_verified_numbers(current_user.id)
owners = await OwnerRepository(db).list_by_phones(numbers)
discs = await repo.list_by_owner_ids([o.id for o in owners])
```

(The exact code depends on the existing `list_discs` shape — preserve the admin/non-admin branching and pagination as they are.)

- [ ] **Step 7: Add an endpoint integration test**

Append to `backend/tests/test_discs.py` (reuse the existing `make_admin` / `admin_headers` helpers):

```python
async def test_admin_create_disc_enqueues_heads_up(db, client):
    from sqlalchemy import select
    from app.models.pickup_event import SMSJob
    from app.models.owner import Owner

    admin = await make_admin(db)
    resp = await client.post(
        "/discs",
        headers=admin_headers(admin.id),
        json={
            "manufacturer": "Innova",
            "name": "Destroyer",
            "color": "red",
            "input_date": "2026-04-01",
            "owner_name": "New Owner",
            "phone_number": "5551234567",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["owner"]["name"] == "New Owner"
    assert body["owner"]["phone_number"] == "+15551234567"

    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert len(jobs) == 1
    assert "New Owner" in jobs[0].message

    owner = (await db.execute(select(Owner))).scalar_one()
    assert owner.heads_up_sent_at is not None


async def test_admin_create_second_disc_same_owner_skips_heads_up(db, client):
    from sqlalchemy import select
    from app.models.pickup_event import SMSJob

    admin = await make_admin(db)
    for _ in range(2):
        resp = await client.post(
            "/discs",
            headers=admin_headers(admin.id),
            json={
                "manufacturer": "Innova",
                "name": "Destroyer",
                "color": "red",
                "input_date": "2026-04-01",
                "owner_name": "Repeat Owner",
                "phone_number": "5557778888",
            },
        )
        assert resp.status_code == 201

    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert len(jobs) == 1
```

- [ ] **Step 8: Run the full disc test module**

Run: `cd backend && pytest tests/test_discs.py tests/test_owners.py -v`

Expected: PASS. Some existing tests may reference `disc["owner_name"]` or `disc["phone_number"]` in the response JSON — update them to `disc["owner"]["name"]` / `disc["owner"]["phone_number"]` (or `assert disc["owner"] is None`). Fix as needed.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/heads_up.py backend/app/routers/discs.py backend/tests/test_discs.py backend/tests/test_owners.py
git commit -m "feat(owner): admin disc create resolves owner and sends heads-up"
```

---

## Task 8: Wishlist and `/me` routes

**Files:**
- Modify: `backend/app/routers/users.py`
- Test: `backend/tests/test_users.py`

- [ ] **Step 1: Update test expectations**

Open `backend/tests/test_users.py`. Any test that:
- Creates a disc with `owner_name`/`phone_number` at the model/repo layer needs to resolve an Owner first, OR pass `owner_id=...` to `DiscRepository.create`.
- Reads `owner_name`/`phone_number` from a disc response needs to read `owner.name` / `owner.phone_number`.

Find and update them (should be straightforward search-and-replace — the file is under 200 lines).

- [ ] **Step 2: Update `add_wishlist_disc`**

Replace the `add_wishlist_disc` body (at `backend/app/routers/users.py:118` in the pre-refactor code) with:

```python
@router.post("/me/wishlist", response_model=DiscOut, status_code=201, operation_id="addWishlistDisc")
async def add_wishlist_disc(
    body: WishlistDiscCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Disc:
    verified = await UserRepository(db).get_verified_numbers(current_user.id)
    if body.phone_number not in verified:
        raise HTTPException(status_code=400, detail="Phone number not verified")

    owner_name = body.owner_name or current_user.name
    owner = await OwnerRepository(db).resolve_or_create(
        name=owner_name, phone_number=body.phone_number
    )
    disc = await DiscRepository(db).create(
        manufacturer=body.manufacturer or "",
        name=body.name or "",
        color=body.color or "",
        input_date=date.today(),
        owner_id=owner.id,
        is_found=False,
    )
    # No heads-up for wishlist.
    await db.commit()
    return await DiscRepository(db).get_by_id(disc.id)
```

Add imports as needed (`from app.repositories.owner import OwnerRepository`, `from datetime import date`).

- [ ] **Step 3: Update `get_my_discs` and `get_my_wishlist`**

Replace the body of each with:

```python
@router.get("/me/discs", response_model=list[DiscOut], operation_id="getMyDiscs")
async def get_my_discs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Disc]:
    numbers = await UserRepository(db).get_verified_numbers(current_user.id)
    owners = await OwnerRepository(db).list_by_phones(numbers)
    return await DiscRepository(db).list_found_by_owner_ids([o.id for o in owners])


@router.get("/me/wishlist", response_model=list[DiscOut], operation_id="getMyWishlist")
async def get_my_wishlist(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Disc]:
    numbers = await UserRepository(db).get_verified_numbers(current_user.id)
    owners = await OwnerRepository(db).list_by_phones(numbers)
    return await DiscRepository(db).list_wishlist_by_owner_ids([o.id for o in owners])
```

- [ ] **Step 4: Add/update a wishlist integration test**

Append to `backend/tests/test_users.py`:

```python
async def test_wishlist_add_resolves_owner_no_heads_up(db, client):
    from sqlalchemy import select
    from app.models.pickup_event import SMSJob
    from app.models.owner import Owner
    # Create user and verify a phone (use the existing test helpers)
    user = await make_user_with_verified_phone(db, phone="+15551112222")
    resp = await client.post(
        "/me/wishlist",
        headers=user_headers(user.id),
        json={"phone_number": "5551112222", "manufacturer": "Innova",
              "name": "Leopard", "color": "blue"},
    )
    assert resp.status_code == 201
    assert resp.json()["owner"]["phone_number"] == "+15551112222"

    # No SMS jobs for wishlist
    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert jobs == []

    # Owner row exists and is marked "not yet contacted"
    owner = (await db.execute(select(Owner))).scalar_one()
    assert owner.heads_up_sent_at is None
```

If `make_user_with_verified_phone` / `user_headers` don't exist, look for their equivalents in the current `test_users.py` and use whatever pattern is already there (do not invent fixtures).

- [ ] **Step 5: Run the user test module**

Run: `cd backend && pytest tests/test_users.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/users.py backend/tests/test_users.py
git commit -m "refactor(owner): /me and wishlist routes use owner_id"
```

---

## Task 9: Notification service groups by `owner_id`

**Files:**
- Modify: `backend/app/services/notification.py`
- Test: `backend/tests/test_worker.py` (if it covers notifications) or add to `backend/tests/test_owners.py`

- [ ] **Step 1: Write a failing test**

Append to `backend/tests/test_owners.py`:

```python
async def test_notification_groups_by_owner(db):
    from datetime import date, datetime, timezone
    from app.repositories.owner import OwnerRepository
    from app.repositories.disc import DiscRepository
    from app.repositories.pickup_event import PickupEventRepository
    from app.services.notification import enqueue_pickup_notifications
    from app.models.pickup_event import SMSJob
    from sqlalchemy import select

    o1 = await OwnerRepository(db).resolve_or_create(
        name="Leo", phone_number="+15559000001"
    )
    o2 = await OwnerRepository(db).resolve_or_create(
        name="Mia", phone_number="+15559000002"
    )
    disc_repo = DiscRepository(db)
    await disc_repo.create(manufacturer="i", name="n", color="r",
                           input_date=date(2026,4,1), owner_id=o1.id)
    await disc_repo.create(manufacturer="i", name="n", color="g",
                           input_date=date(2026,4,1), owner_id=o1.id)
    await disc_repo.create(manufacturer="d", name="b", color="y",
                           input_date=date(2026,4,1), owner_id=o2.id)
    event = await PickupEventRepository(db).create(
        start_at=datetime(2026, 5, 1, 20, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 5, 1, 22, 0, tzinfo=timezone.utc),
        notes=None,
    )
    await db.commit()

    sms_count, disc_count = await enqueue_pickup_notifications(event, db)
    await db.commit()
    assert disc_count == 3
    assert sms_count == 2  # one per owner

    jobs = (await db.execute(select(SMSJob))).scalars().all()
    # Exclude any heads-up jobs (there shouldn't be any here since owners were
    # created via the repo, not the admin create flow).
    phones = sorted(j.phone_number for j in jobs)
    assert phones == ["+15559000001", "+15559000002"]
```

- [ ] **Step 2: Run to see failure**

Run: `cd backend && pytest tests/test_owners.py::test_notification_groups_by_owner -v`

Expected: FAIL — `disc.phone_number` attribute missing.

- [ ] **Step 3: Update `backend/app/services/notification.py`**

```python
# backend/app/services/notification.py
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.disc import DiscRepository
from app.repositories.pickup_event import PickupEventRepository
from app.models.pickup_event import PickupEvent
from app.core.timezone import COURSE_TIMEZONE


FINAL_NOTICE_THRESHOLD = 6


async def enqueue_pickup_notifications(
    event: PickupEvent, db: AsyncSession
) -> tuple[int, int]:
    disc_repo = DiscRepository(db)
    event_repo = PickupEventRepository(db)

    unreturned = await disc_repo.list_unreturned_found()
    notified_disc_count = 0
    owner_discs: dict = defaultdict(list)  # owner_id -> [Disc]
    owner_phone: dict = {}                  # owner_id -> phone_number
    owner_is_final: dict = defaultdict(bool)

    for disc in unreturned:
        if disc.owner is None:
            continue
        if await event_repo.disc_already_notified_for_event(disc.id, event.id):
            continue
        prior_count = await event_repo.count_notifications_for_disc(disc.id)
        is_final = prior_count + 1 >= FINAL_NOTICE_THRESHOLD
        await event_repo.create_disc_notification(
            disc_id=disc.id, pickup_event_id=event.id, is_final_notice=is_final
        )
        if is_final:
            await disc_repo.update(disc, final_notice_sent=True)
            owner_is_final[disc.owner_id] = True
        owner_discs[disc.owner_id].append(disc)
        owner_phone[disc.owner_id] = disc.owner.phone_number
        notified_disc_count += 1

    sms_count = 0
    local_start = event.start_at.astimezone(COURSE_TIMEZONE)
    local_end = event.end_at.astimezone(COURSE_TIMEZONE)
    window_str = (
        f"{local_start.strftime('%b %-d')} from "
        f"{local_start.strftime('%-I:%M %p')} to "
        f"{local_end.strftime('%-I:%M %p')} ET"
    )
    for owner_id, discs in owner_discs.items():
        disc_list = ", ".join(
            f"{d.manufacturer} {d.name} ({d.color})" for d in discs
        )
        phone = owner_phone[owner_id]
        if owner_is_final.get(owner_id):
            message = (
                f"FINAL NOTICE: Your disc(s) [{disc_list}] will be added to the "
                f"sale box if not picked up at the {window_str} pickup. "
                "Reply STOP to opt out."
            )
        else:
            message = (
                f"Disc pickup at North Landing {window_str}. "
                f"You have disc(s): {disc_list}. Reply STOP to opt out."
            )
        await event_repo.create_sms_job(phone_number=phone, message=message)
        sms_count += 1

    return sms_count, notified_disc_count
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_owners.py tests/test_worker.py -v`

Expected: PASS. Fix any `test_worker.py` failures by updating references from `disc.phone_number` to `disc.owner.phone_number`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notification.py backend/tests/test_owners.py backend/tests/test_worker.py
git commit -m "refactor(owner): notification service groups by owner_id"
```

---

## Task 10: Suggestions router sources from `owners`

**Files:**
- Modify: `backend/app/routers/suggestions.py`
- Test: `backend/tests/test_suggestions.py`

- [ ] **Step 1: Update the router**

Replace `backend/app/routers/suggestions.py`:

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

router = APIRouter()

SuggestionField = Literal["manufacturer", "name", "color", "owner_name"]


@router.get("", response_model=list[str], operation_id="getSuggestions")
async def get_suggestions(
    field: Annotated[SuggestionField, Query()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[str]:
    if field == "owner_name":
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin required")
        result = await db.execute(
            select(distinct(Owner.name)).order_by(func.lower(Owner.name))
        )
        return [row[0] for row in result.all()]

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
    owner_name: Annotated[str, Query(min_length=1)],
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PhoneSuggestion]:
    # Verified numbers from registered users matching owner_name
    registered_result = await db.execute(
        select(PhoneNumber.number, User.name, User.email)
        .join(User, PhoneNumber.user_id == User.id)
        .where(User.name.ilike(owner_name))
        .where(PhoneNumber.verified.is_(True))
    )
    registered: dict[str, PhoneSuggestion] = {
        row.number: PhoneSuggestion(
            number=row.number,
            label=f"{row.number} — {row.name} ({row.email})",
        )
        for row in registered_result.all()
    }

    # Phone numbers from existing owner records matching this name
    owner_result = await db.execute(
        select(distinct(Owner.phone_number)).where(Owner.name.ilike(owner_name))
    )
    for (number,) in owner_result.all():
        if number not in registered:
            registered[number] = PhoneSuggestion(number=number, label=number)

    return list(registered.values())
```

- [ ] **Step 2: Update `backend/tests/test_suggestions.py`**

Find every test that inserts into `Disc.owner_name` / `Disc.phone_number` and replace with an `Owner` insert via `OwnerRepository`. Then run:

Run: `cd backend && pytest tests/test_suggestions.py -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/suggestions.py backend/tests/test_suggestions.py
git commit -m "refactor(owner): suggestions sourced from owners table"
```

---

## Task 11: Frontend type regen + UI adjustments

**Files:**
- Modify: `frontend/src/api/northlanding.ts` (auto-generated) and any component using the old `disc.owner_name` / `disc.phone_number` shape.
- Modify: `frontend/src/pages/AdminDiscFormPage.tsx`

- [ ] **Step 1: Regenerate the API client**

The project generates types from FastAPI's OpenAPI. Run whatever script the frontend uses (look in `frontend/package.json` for a script named `generate`, `openapi`, or similar). For example: `cd frontend && pnpm run generate:api` or `pnpm run openapi`. If unsure, check the README.

Expected: generated file updates; `DiscOut` now has an `owner: { id, name, phone_number, ... } | null` field instead of `owner_name` / `phone_number`.

- [ ] **Step 2: Fix TypeScript errors**

Run: `cd frontend && pnpm tsc --noEmit` (or the equivalent — check `package.json`).

Walk through each error. The expected replacements are:
- `disc.owner_name` → `disc.owner?.name ?? ''`
- `disc.phone_number` → `disc.owner?.phone_number ?? ''`

In `AdminDiscFormPage.tsx`, the form still submits `owner_name` + `phone_number` (matching `DiscCreate`), so the `DiscFormState` shape and submit payload don't change. Only the code that *reads* `DiscOut` needs updating. When populating the form in edit mode, initialize from `disc.owner?.name` / `disc.owner?.phone_number`.

- [ ] **Step 3: Run the frontend build/test**

Run: `cd frontend && pnpm run build && pnpm run test` (adjust to match the project).

Expected: green.

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "refactor(owner): update frontend for DiscOut.owner shape"
```

---

## Task 12: Full-suite green + final commit

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && pytest -v`

Expected: green. If anything fails, fix in place and commit as `fix(owner): <description>`.

- [ ] **Step 2: Run the app locally end-to-end**

Run the backend and frontend dev servers. Verify manually:
- Log a new disc with a fresh `(name, phone)` → SMS intro enqueued (inspect `sms_jobs` table).
- Log a second disc for the same owner → no new intro SMS.
- Log a disc with matching phone but different name → new intro SMS (different owner row).
- Log a disc with no owner info → no SMS, `disc.owner_id IS NULL`.
- Log in as a user with a verified phone that matches an owner → `/me/discs` returns that disc.
- Admin autocomplete for owner name and phone shows values from the owners table.

- [ ] **Step 3: Final commit (only if anything was tweaked)**

```bash
git add -A
git commit -m "chore(owner): e2e verification touch-ups"
```

---

## Self-Review Notes

- Every spec section — new table, migration/backfill, heads-up trigger, user→disc lookup, autocomplete, notification service — maps to a task.
- Placeholders: the migration header keeps `revision` / `down_revision` auto-generated (called out inline). The frontend test/build commands are described generically because the exact script names are project-specific — the engineer must read `package.json`.
- Type consistency: `OwnerOut` fields match `Owner` model; `DiscOut.owner: OwnerOut | None` matches the `Disc.owner` relationship; repository method names (`list_found_by_owner_ids`, `list_wishlist_by_owner_ids`, `list_by_owner_ids`) are consistent between Task 6 and their callers in Tasks 8–9.
- Known areas requiring engineer judgment: (a) exact location to import `Owner` so SQLAlchemy registers it (Task 3 step 3); (b) adjusting existing tests that reference the old `owner_name` / `phone_number` response fields (Tasks 7–10); (c) frontend generator script name (Task 11). Each is flagged inline.
