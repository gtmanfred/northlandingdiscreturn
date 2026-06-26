# Welcome SMS + Heads-up Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send a one-time welcome SMS to every new owner explaining the app and how to connect their number at discreturn.nl, and rework the heads-up SMS to drop the intro/cadence text and include the found disc's details.

**Architecture:** New `welcome.py` service mirrors the existing `heads_up.py` pattern. A new nullable `owners.welcome_sent_at` column dedupes the welcome (once per owner, any `is_found`). In `create_disc`, welcome is enqueued before heads-up so its `SMSJob` row is inserted/sent first. `maybe_enqueue_heads_up` changes signature to take the `disc` object so it can render disc details.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, pytest (async).

---

## File Structure

- Create: `backend/app/services/welcome.py` — welcome template + `maybe_enqueue_welcome`.
- Create: `backend/alembic/versions/b1c2d3e4f5a6_add_welcome_sent_at_to_owners.py` — migration.
- Modify: `backend/app/models/owner.py` — add `welcome_sent_at` column.
- Modify: `backend/app/repositories/owner.py` — add `mark_welcome_sent`.
- Modify: `backend/app/services/heads_up.py` — new template, new signature.
- Modify: `backend/app/routers/discs.py:92-93` — call welcome then heads-up.
- Modify: `backend/tests/test_discs.py:305-359` — update job-count assertions.
- Modify: `docs/disc-sms-flow.md` — diagram + templates.
- Test: `backend/tests/test_owners.py`, `backend/tests/test_discs.py`.

All `pytest` / `alembic` commands run from `backend/`.

---

### Task 1: Add `welcome_sent_at` column to Owner model

**Files:**
- Modify: `backend/app/models/owner.py:28-30`
- Test: `backend/tests/test_owners.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_owners.py`:

```python
async def test_repo_mark_welcome_sent(db):
    repo = OwnerRepository(db)
    owner = await repo.resolve_or_create(first_name="W", last_name="", phone_number="+15554440000")
    await db.commit()
    assert owner.welcome_sent_at is None
    await repo.mark_welcome_sent(owner)
    await db.commit()
    await db.refresh(owner)
    assert owner.welcome_sent_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_owners.py::test_repo_mark_welcome_sent -v`
Expected: FAIL — `AttributeError: 'Owner' object has no attribute 'welcome_sent_at'` (and `OwnerRepository` has no `mark_welcome_sent`).

- [ ] **Step 3: Add the column**

In `backend/app/models/owner.py`, after the `heads_up_sent_at` block (line 28-30), add:

```python
    welcome_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 4: Add the repository method**

In `backend/app/repositories/owner.py`, after `mark_heads_up_sent` (line 46-50), add:

```python
    async def mark_welcome_sent(self, owner: Owner) -> Owner:
        owner.welcome_sent_at = func.now()
        await self.db.flush()
        await self.db.refresh(owner)
        return owner
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_owners.py::test_repo_mark_welcome_sent -v`
Expected: PASS.

(Tests use a fresh schema created from the models, so no migration is needed for tests to pass. The migration in Task 2 is for real databases.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/owner.py backend/app/repositories/owner.py backend/tests/test_owners.py
git commit -m "feat: add welcome_sent_at column and mark_welcome_sent"
```

---

### Task 2: Alembic migration for `welcome_sent_at`

**Files:**
- Create: `backend/alembic/versions/b1c2d3e4f5a6_add_welcome_sent_at_to_owners.py`

- [ ] **Step 1: Create the migration file**

Create `backend/alembic/versions/b1c2d3e4f5a6_add_welcome_sent_at_to_owners.py`:

```python
"""add_welcome_sent_at_to_owners

Revision ID: b1c2d3e4f5a6
Revises: a73e1f8ff264
Create Date: 2026-06-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a73e1f8ff264'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('owners', sa.Column('welcome_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('owners', 'welcome_sent_at')
```

- [ ] **Step 2: Verify the migration applies**

Run: `alembic upgrade head`
Expected: runs without error; `owners.welcome_sent_at` exists. (If no DB is available locally, instead run `alembic heads` and confirm `b1c2d3e4f5a6` is the single head.)

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/b1c2d3e4f5a6_add_welcome_sent_at_to_owners.py
git commit -m "feat: migration adding owners.welcome_sent_at"
```

---

### Task 3: Welcome service

**Files:**
- Create: `backend/app/services/welcome.py`
- Test: `backend/tests/test_discs.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_discs.py`:

```python
async def test_welcome_sms_sent_for_wishlist_owner(db, client):
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
            "owner_first_name": "Wish",
            "owner_last_name": "List",
            "phone_number": "5552220000",
            "is_found": False,
        },
    )
    assert resp.status_code == 201

    jobs = (await db.execute(select(SMSJob))).scalars().all()
    # wishlist disc => no heads-up, only welcome
    assert len(jobs) == 1
    assert "discreturn.nl" in jobs[0].message

    owner = (await db.execute(select(Owner))).scalar_one()
    assert owner.welcome_sent_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discs.py::test_welcome_sms_sent_for_wishlist_owner -v`
Expected: FAIL — no welcome enqueued (`assert len(jobs) == 1` fails with 0 jobs, since wishlist skips heads-up and welcome doesn't exist yet).

- [ ] **Step 3: Create the welcome service**

Create `backend/app/services/welcome.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.owner import Owner
from app.repositories.owner import OwnerRepository
from app.repositories.pickup_event import PickupEventRepository


WELCOME_TEMPLATE = (
    "Hi {name}, this is North Landing Disc Return — we reunite lost discs with "
    "their owners. To see what discs have been found and get pickup updates, go "
    "to discreturn.nl, sign up, and connect this phone number to your profile. "
    "Reply STOP to opt out."
)


async def maybe_enqueue_welcome(*, owner: Owner, db: AsyncSession) -> bool:
    """Enqueue the one-time welcome SMS to this owner. Returns True if enqueued."""
    if owner.welcome_sent_at is not None:
        return False
    message = WELCOME_TEMPLATE.format(name=owner.name)
    await PickupEventRepository(db).create_sms_job(
        phone_number=owner.phone_number, message=message
    )
    await OwnerRepository(db).mark_welcome_sent(owner)
    return True
```

- [ ] **Step 4: Wire welcome into create_disc**

In `backend/app/routers/discs.py`, add the import near line 14:

```python
from app.services.welcome import maybe_enqueue_welcome
```

Replace the block at lines 92-93:

```python
    if owner_obj is not None:
        await maybe_enqueue_heads_up(owner=owner_obj, is_found=disc.is_found, db=db)
```

with (welcome first, heads-up second — note heads-up now takes `disc`):

```python
    if owner_obj is not None:
        await maybe_enqueue_welcome(owner=owner_obj, db=db)
        await maybe_enqueue_heads_up(owner=owner_obj, disc=disc, db=db)
```

(`maybe_enqueue_heads_up`'s new `disc=` signature lands in Task 4. If running tasks strictly in order, this line will raise `TypeError` until Task 4 — that is expected and Task 4's tests cover it. To keep Task 3 green in isolation, you may temporarily keep `is_found=disc.is_found`; the final state after Task 4 must be `disc=disc`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_discs.py::test_welcome_sms_sent_for_wishlist_owner -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/welcome.py backend/app/routers/discs.py backend/tests/test_discs.py
git commit -m "feat: send one-time welcome SMS to new owners"
```

---

### Task 4: Rework heads-up template + signature (include disc details)

**Files:**
- Modify: `backend/app/services/heads_up.py:7-27`
- Test: `backend/tests/test_discs.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_discs.py`:

```python
async def test_heads_up_includes_disc_details(db, client):
    from sqlalchemy import select
    from app.models.pickup_event import SMSJob

    admin = await make_admin(db)
    resp = await client.post(
        "/discs",
        headers=admin_headers(admin.id),
        json={
            "manufacturer": "Innova",
            "name": "Destroyer",
            "color": "red",
            "input_date": "2026-04-01",
            "owner_first_name": "Found",
            "owner_last_name": "Owner",
            "phone_number": "5553330000",
        },
    )
    assert resp.status_code == 201

    jobs = (await db.execute(select(SMSJob))).scalars().all()
    # new found-disc owner => welcome + heads-up
    assert len(jobs) == 2
    heads_up = [j for j in jobs if "We found one of your discs" in j.message]
    assert len(heads_up) == 1
    assert "Innova Destroyer (red)" in heads_up[0].message
    assert "discreturn.nl" not in heads_up[0].message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discs.py::test_heads_up_includes_disc_details -v`
Expected: FAIL — heads-up text lacks disc details (and `maybe_enqueue_heads_up` signature mismatch if Task 3 used `disc=`).

- [ ] **Step 3: Rework heads_up.py**

Replace the entire contents of `backend/app/services/heads_up.py` with:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.disc import Disc
from app.models.owner import Owner
from app.repositories.owner import OwnerRepository
from app.repositories.pickup_event import PickupEventRepository


HEADS_UP_TEMPLATE = (
    "Hi {name}, this is North Landing Disc Return. We found one of your discs: "
    "{disc_desc}. Reply STOP to opt out."
)


async def maybe_enqueue_heads_up(*, owner: Owner, disc: Disc, db: AsyncSession) -> bool:
    """Enqueue the one-time found-disc SMS to this owner. Returns True if enqueued."""
    if not disc.is_found:
        return False
    if owner.heads_up_sent_at is not None:
        return False
    disc_desc = f"{disc.manufacturer} {disc.name} ({disc.color})"
    message = HEADS_UP_TEMPLATE.format(name=owner.name, disc_desc=disc_desc)
    await PickupEventRepository(db).create_sms_job(
        phone_number=owner.phone_number, message=message
    )
    await OwnerRepository(db).mark_heads_up_sent(owner)
    return True
```

- [ ] **Step 4: Confirm the router uses `disc=`**

Ensure `backend/app/routers/discs.py` calls:

```python
        await maybe_enqueue_heads_up(owner=owner_obj, disc=disc, db=db)
```

(If you left `is_found=disc.is_found` temporarily in Task 3, change it to `disc=disc` now.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_discs.py::test_heads_up_includes_disc_details -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/heads_up.py backend/app/routers/discs.py backend/tests/test_discs.py
git commit -m "feat: heads-up SMS carries disc details, drops intro text"
```

---

### Task 5: Fix existing job-count assertions

The two existing heads-up tests assert old job counts. A new found-disc owner now produces 2 jobs (welcome + heads-up); a repeat owner produces 2 total (both gated on the 2nd create).

**Files:**
- Modify: `backend/tests/test_discs.py:305-359`

- [ ] **Step 1: Update `test_admin_create_disc_enqueues_heads_up`**

In `backend/tests/test_discs.py`, change the assertions at lines 329-331 from:

```python
    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert len(jobs) == 1
    assert "New Owner" in jobs[0].message
```

to:

```python
    jobs = (await db.execute(select(SMSJob))).scalars().all()
    # welcome + heads-up
    assert len(jobs) == 2
    assert all("New Owner" in j.message for j in jobs)
    assert any("We found one of your discs" in j.message for j in jobs)
    assert any("discreturn.nl" in j.message for j in jobs)
```

- [ ] **Step 2: Update `test_admin_create_second_disc_same_owner_skips_heads_up`**

Change the assertion at lines 358-359 from:

```python
    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert len(jobs) == 1
```

to:

```python
    jobs = (await db.execute(select(SMSJob))).scalars().all()
    # first create => welcome + heads-up; second create => both gated, none added
    assert len(jobs) == 2
```

- [ ] **Step 3: Run the full disc + owner suites**

Run: `pytest tests/test_discs.py tests/test_owners.py -v`
Expected: PASS (all, including the two updated tests and the three new tests).

- [ ] **Step 4: Run the whole backend test suite**

Run: `pytest`
Expected: PASS. (Check `tests/test_users.py::test_wishlist_add_resolves_owner_no_heads_up` still passes — wishlist still leaves `heads_up_sent_at` NULL; it now also enqueues a welcome, but that test only asserts `heads_up_sent_at is None`, which remains true.)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_discs.py
git commit -m "test: update job-count assertions for welcome SMS"
```

---

### Task 6: Update SMS flow doc

**Files:**
- Modify: `docs/disc-sms-flow.md`

- [ ] **Step 1: Add welcome to the SMS send-points list**

In `docs/disc-sms-flow.md`, under "## SMS send points", change the intro line "There are exactly **two** places an SMS is enqueued:" to "**three**" and add a welcome bullet before heads-up:

```markdown
1. **Welcome** — fired once per owner the first time their phone number is entered
   (any disc, found or wishlist). Explains the app + how to connect their number at
   discreturn.nl.
2. **Heads-up** — fired once per owner when a *found* disc with owner info is created;
   names the found disc.
3. **Pickup notification** — fired manually by an admin per pickup event; regular or
   final-notice variant.
```

- [ ] **Step 2: Update the mermaid diagram**

In the `flowchart TD` block, replace the heads-up branch (the `F`/`G`/`H`/`I` nodes) with a welcome step that runs before heads-up:

```
    E --> WEL{maybe_enqueue_welcome<br/>owner.welcome_sent_at is NULL?}
    WEL -- yes --> WG[[SMSJob: Template 0<br/>WELCOME]]
    WG --> WH[stamp owner.welcome_sent_at]
    WH --> F
    WEL -- no --> F
    F{maybe_enqueue_heads_up<br/>is_found AND<br/>owner.heads_up_sent_at is NULL?}
    F -- yes --> G[[SMSJob: Template 1<br/>HEADS-UP + disc details]]
    G --> H[stamp owner.heads_up_sent_at]
    F -- no --> I[no heads-up]
```

Also add `WG` to the worker subgraph enqueue edges alongside `G`, `AE`, `AF`:

```
        WG -.enqueued.-> WJ
```

- [ ] **Step 3: Add Template 0 and update Template 1**

In "## Message templates", add a new section before "### Template 1 — Heads-up":

```markdown
### Template 0 — Welcome

Source: `backend/app/services/welcome.py`

> Hi {name}, this is North Landing Disc Return — we reunite lost discs with their
> owners. To see what discs have been found and get pickup updates, go to discreturn.nl,
> sign up, and connect this phone number to your profile. Reply STOP to opt out.

- `{name}` = owner full name, e.g. `Jane Smith`.
- Fires for **any** new owner, including wishlist (`is_found=false`) discs.
```

Then replace the Template 1 quote with the reworked text:

```markdown
> Hi {name}, this is North Landing Disc Return. We found one of your discs: {disc_desc}.
> Reply STOP to opt out.

- `{disc_desc}` = `Manufacturer Name (Color)`, e.g. `Innova Destroyer (red)`.
```

- [ ] **Step 4: Update the "Key rules" section**

In "## Key rules", add a bullet:

```markdown
- **Welcome is once per owner, ever** — gated on `owner.welcome_sent_at`, independent of
  `is_found`. Enqueued before heads-up, so a new found-disc owner gets welcome first,
  then heads-up (two texts).
```

- [ ] **Step 5: Commit**

```bash
git add docs/disc-sms-flow.md
git commit -m "docs: add welcome SMS to disc flow diagram and templates"
```

---

## Self-Review Notes

- **Spec coverage:** welcome service (Task 3), dedup column + migration (Tasks 1-2), heads-up rework with disc details (Task 4), ordering welcome-before-heads-up (Task 3 router edit), doc update (Task 6), existing-test fixups (Task 5). All spec sections covered.
- **Type consistency:** `maybe_enqueue_welcome(*, owner, db)`, `maybe_enqueue_heads_up(*, owner, disc, db)`, `mark_welcome_sent(owner)`, `WELCOME_TEMPLATE` / `HEADS_UP_TEMPLATE` used consistently across tasks.
- **No backfill** (per decision): existing owners have `welcome_sent_at = NULL` and would receive a welcome on their next disc-add. The operator gates this via `SMS_TEST_MODE` + `SMS_ALLOWLIST` during bulk loads.
- **Disc desc format** matches pickup notifications: `f"{manufacturer} {name} ({color})"`.
