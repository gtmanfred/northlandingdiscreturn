# SMS STOP/START Opt-Out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record SMS opt-out when a recipient replies STOP, clear it on START, and never send queued SMS to an opted-out number.

**Architecture:** A dedicated `sms_opt_out` table keyed on phone number is the single source of truth (row present = opted out). The Surge inbound webhook writes that table on STOP/START. The SMS worker checks it at send-time and marks opted-out jobs `skipped` instead of sending — one enforcement point covering every enqueue path.

**Tech Stack:** FastAPI, SQLAlchemy 2.x async, Alembic, PostgreSQL, httpx, pytest + pytest-asyncio (`asyncio_mode=auto`).

## Global Constraints

- Python 3.12; SQLAlchemy 2.x declarative `Mapped`/`mapped_column` style.
- All DB access is async via `AsyncSession`. Repositories take `db` in `__init__`.
- Tests are async, no `@pytest.mark.asyncio` decorator needed (auto mode).
- Test schema is built by `Base.metadata.create_all` (conftest `engine` fixture) — any new model must be imported in `app/models/__init__.py` to be created; new Python enum values exist automatically in the test DB.
- Keyword match is exact against the already-uppercased, stripped body: `"STOP"` / `"START"` only.
- No confirmation/auto-reply SMS.
- Phone numbers are matched as exact strings (expected E.164 from Surge).
- Commit after each task. Use `git commit --no-verify` only if pre-commit hooks fail for environment reasons.

---

### Task 1: SMSOptOut model + repository

**Files:**
- Create: `app/models/sms_opt_out.py`
- Modify: `app/models/__init__.py`
- Create: `app/repositories/sms_opt_out.py`
- Test: `tests/test_sms_opt_out.py`

**Interfaces:**
- Consumes: `app.models.base.Base`, `AsyncSession`.
- Produces:
  - `SMSOptOut` model (`__tablename__ = "sms_opt_out"`, columns `id`, `phone_number`, `opted_out_at`).
  - `SMSOptOutRepository(db: AsyncSession)` with:
    - `async def opt_out(self, phone_number: str) -> None`
    - `async def opt_in(self, phone_number: str) -> None`
    - `async def is_opted_out(self, phone_number: str) -> bool`

- [ ] **Step 1: Write the failing repository test**

Create `tests/test_sms_opt_out.py`:

```python
# backend/tests/test_sms_opt_out.py
from app.repositories.sms_opt_out import SMSOptOutRepository


async def test_opt_out_then_is_opted_out(db):
    repo = SMSOptOutRepository(db)
    assert await repo.is_opted_out("+15551234567") is False
    await repo.opt_out("+15551234567")
    assert await repo.is_opted_out("+15551234567") is True


async def test_opt_out_is_idempotent(db):
    repo = SMSOptOutRepository(db)
    await repo.opt_out("+15551234567")
    await repo.opt_out("+15551234567")
    assert await repo.is_opted_out("+15551234567") is True


async def test_opt_in_removes_opt_out(db):
    repo = SMSOptOutRepository(db)
    await repo.opt_out("+15551234567")
    await repo.opt_in("+15551234567")
    assert await repo.is_opted_out("+15551234567") is False


async def test_opt_in_on_unknown_number_is_noop(db):
    repo = SMSOptOutRepository(db)
    await repo.opt_in("+15550000000")  # no error
    assert await repo.is_opted_out("+15550000000") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_sms_opt_out.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repositories.sms_opt_out'`

- [ ] **Step 3: Create the model**

Create `app/models/sms_opt_out.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class SMSOptOut(Base):
    __tablename__ = "sms_opt_out"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_number: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    opted_out_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Register the model**

Modify `app/models/__init__.py` — add the import and `__all__` entry:

```python
from app.models.sms_opt_out import SMSOptOut
```

Add `"SMSOptOut",` to the `__all__` list.

- [ ] **Step 5: Create the repository**

Create `app/repositories/sms_opt_out.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sms_opt_out import SMSOptOut


class SMSOptOutRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get(self, phone_number: str) -> SMSOptOut | None:
        result = await self.db.execute(
            select(SMSOptOut).where(SMSOptOut.phone_number == phone_number)
        )
        return result.scalar_one_or_none()

    async def is_opted_out(self, phone_number: str) -> bool:
        return await self._get(phone_number) is not None

    async def opt_out(self, phone_number: str) -> None:
        if await self._get(phone_number) is None:
            self.db.add(SMSOptOut(phone_number=phone_number))
            await self.db.flush()

    async def opt_in(self, phone_number: str) -> None:
        existing = await self._get(phone_number)
        if existing is not None:
            await self.db.delete(existing)
            await self.db.flush()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sms_opt_out.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: Commit**

```bash
git add app/models/sms_opt_out.py app/models/__init__.py app/repositories/sms_opt_out.py tests/test_sms_opt_out.py
git commit -m "feat(sms): add SMSOptOut model and repository"
```

---

### Task 2: Webhook STOP/START handling

**Files:**
- Modify: `app/routers/webhooks.py`
- Test: `tests/test_webhooks.py`

**Interfaces:**
- Consumes: `SMSOptOutRepository` (Task 1), `get_db` from `app.database`.
- Produces: `surge_inbound` now writes opt-out state; response shape unchanged for existing event types.

- [ ] **Step 1: Write the failing webhook tests**

Add to `tests/test_webhooks.py` (the `_payload`, `make_surge_signature`, and `settings` helpers already exist in this file). Add an import at the top:

```python
from app.repositories.sms_opt_out import SMSOptOutRepository
```

Append these tests:

```python
async def _post_signed(client, raw: bytes):
    ts = int(time.time())
    sig = make_surge_signature(raw, settings.SURGE_WEBHOOK_SIGNING_SECRET, ts)
    return await client.post(
        "/webhooks/sms",
        content=raw,
        headers={"Surge-Signature": sig, "Content-Type": "application/json"},
    )


async def test_stop_creates_opt_out(client, db):
    resp = await _post_signed(client, _payload(body="STOP", phone="+15551112222"))
    assert resp.status_code == 200
    assert await SMSOptOutRepository(db).is_opted_out("+15551112222") is True


async def test_lowercase_stop_creates_opt_out(client, db):
    resp = await _post_signed(client, _payload(body="stop", phone="+15551112222"))
    assert resp.status_code == 200
    assert await SMSOptOutRepository(db).is_opted_out("+15551112222") is True


async def test_start_removes_opt_out(client, db):
    await SMSOptOutRepository(db).opt_out("+15551112222")
    resp = await _post_signed(client, _payload(body="START", phone="+15551112222"))
    assert resp.status_code == 200
    assert await SMSOptOutRepository(db).is_opted_out("+15551112222") is False


async def test_duplicate_stop_is_idempotent(client, db):
    await _post_signed(client, _payload(body="STOP", phone="+15551112222"))
    await _post_signed(client, _payload(body="STOP", phone="+15551112222"))
    assert await SMSOptOutRepository(db).is_opted_out("+15551112222") is True


async def test_non_keyword_body_does_not_change_state(client, db):
    resp = await _post_signed(client, _payload(body="hello there", phone="+15551112222"))
    assert resp.status_code == 200
    assert await SMSOptOutRepository(db).is_opted_out("+15551112222") is False


async def test_empty_from_number_does_not_error(client, db):
    raw = json.dumps({
        "type": "message.received",
        "id": "evt_test",
        "data": {"body": "STOP", "conversation": {"contact": {"phone_number": ""}}},
    }).encode()
    resp = await _post_signed(client, raw)
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_webhooks.py -k "opt_out or start or stop or non_keyword or empty_from" -v`
Expected: FAIL — opt-out state not written (e.g. `test_stop_creates_opt_out` asserts True but gets False).

- [ ] **Step 3: Add the DB dependency and keyword handling**

Modify `app/routers/webhooks.py`. Update imports near the top:

```python
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories.sms_opt_out import SMSOptOutRepository
```

Replace the `surge_inbound` handler (currently `webhooks.py:46-61`) with:

```python
@router.post("/sms", operation_id="surgeWebhook", include_in_schema=False)
async def surge_inbound(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    signature = request.headers.get("Surge-Signature", "")
    if not validate_surge_signature(raw, signature, settings.SURGE_WEBHOOK_SIGNING_SECRET):
        raise HTTPException(status_code=403, detail="Invalid Surge signature")

    payload = json.loads(raw)
    if payload.get("type") != "message.received":
        return {"status": "ignored"}

    data = payload.get("data") or {}
    body = (data.get("body") or "").strip().upper()
    contact = (data.get("conversation") or {}).get("contact") or {}
    from_number = contact.get("phone_number", "")

    if from_number:
        opt_out_repo = SMSOptOutRepository(db)
        if body == "STOP":
            await opt_out_repo.opt_out(from_number)
        elif body == "START":
            await opt_out_repo.opt_in(from_number)

    return {"status": "received", "from": from_number, "body": body}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_webhooks.py -v`
Expected: PASS (existing webhook tests + new ones all pass)

- [ ] **Step 5: Commit**

```bash
git add app/routers/webhooks.py tests/test_webhooks.py
git commit -m "feat(sms): handle STOP/START in Surge inbound webhook"
```

---

### Task 3: Worker send-time enforcement + `skipped` status

**Files:**
- Modify: `app/models/pickup_event.py` (add `skipped` enum value)
- Modify: `app/repositories/pickup_event.py` (add `mark_sms_skipped`)
- Modify: `worker/main.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `SMSOptOutRepository` (Task 1), `SMSJobStatus`, `PickupEventRepository`.
- Produces:
  - `SMSJobStatus.skipped`
  - `PickupEventRepository.mark_sms_skipped(self, job: SMSJob) -> None`
  - `process_sms_jobs` skips opted-out numbers without an HTTP call.

- [ ] **Step 1: Write the failing worker test**

Add to `tests/test_worker.py`. Add an import near the top:

```python
from app.repositories.sms_opt_out import SMSOptOutRepository
```

Append:

```python
async def test_process_sms_jobs_skips_opted_out(db, monkeypatch):
    repo = PickupEventRepository(db)
    await SMSOptOutRepository(db).opt_out("+15551234567")
    job = await repo.create_sms_job(phone_number="+15551234567", message="Test notice")
    await db.commit()

    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", _make_async_client_factory(transport))

    await worker_main.process_sms_jobs(db)

    assert captured == []  # no HTTP call made
    await db.refresh(job)
    assert job.status == SMSJobStatus.skipped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_worker.py::test_process_sms_jobs_skips_opted_out -v`
Expected: FAIL — `AttributeError: skipped` (enum value missing) or the job is sent (`captured` non-empty).

- [ ] **Step 3: Add the `skipped` enum value**

Modify `app/models/pickup_event.py` — add to `SMSJobStatus` (after `failed`, `pickup_event.py:14`):

```python
class SMSJobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"
```

- [ ] **Step 4: Add `mark_sms_skipped` to the repository**

Modify `app/repositories/pickup_event.py` — add after `mark_sms_failed` (`pickup_event.py:120`):

```python
    async def mark_sms_skipped(self, job: SMSJob) -> None:
        job.status = SMSJobStatus.skipped
        job.processed_at = datetime.now(timezone.utc)
        await self.db.flush()
```

- [ ] **Step 5: Add the enforcement check in the worker**

Modify `worker/main.py`. Add the import:

```python
from app.repositories.sms_opt_out import SMSOptOutRepository
```

Replace the job loop body in `process_sms_jobs` (`worker/main.py:30-38`) with:

```python
        opt_out_repo = SMSOptOutRepository(db)
        async with httpx.AsyncClient() as client:
            for job in jobs:
                if await opt_out_repo.is_opted_out(job.phone_number):
                    await repo.mark_sms_skipped(job)
                    logger.info(f"SMS skipped (opted out): {job.phone_number}")
                    continue
                try:
                    await send_sms_async(client, job.phone_number, job.message)
                    await repo.mark_sms_sent(job)
                    logger.info(f"SMS sent to {job.phone_number}")
                except Exception as e:
                    await repo.mark_sms_failed(job, str(e))
                    logger.error(f"SMS failed to {job.phone_number}: {e}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_worker.py -v`
Expected: PASS (existing send/fail tests + new skip test)

- [ ] **Step 7: Commit**

```bash
git add app/models/pickup_event.py app/repositories/pickup_event.py worker/main.py tests/test_worker.py
git commit -m "feat(sms): skip opted-out numbers at worker send-time"
```

---

### Task 4: Alembic migration

**Files:**
- Create: `alembic/versions/e4f5a6b7c8d9_add_sms_opt_out_and_skipped_status.py`

**Interfaces:**
- Consumes: current head revision `d3e4f5a6b7c8`.
- Produces: `sms_opt_out` table and the `skipped` value on the `smsjobstatus` PG enum in a real database.

- [ ] **Step 1: Create the migration**

Create `alembic/versions/e4f5a6b7c8d9_add_sms_opt_out_and_skipped_status.py`:

```python
"""add_sms_opt_out_and_skipped_status

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE smsjobstatus ADD VALUE IF NOT EXISTS 'skipped'")

    op.create_table(
        'sms_opt_out',
        sa.Column('id', PG_UUID(as_uuid=True), primary_key=True),
        sa.Column('phone_number', sa.String(), nullable=False),
        sa.Column(
            'opted_out_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint('phone_number', name='uq_sms_opt_out_phone_number'),
    )
    op.create_index('ix_sms_opt_out_phone_number', 'sms_opt_out', ['phone_number'])


def downgrade() -> None:
    op.drop_index('ix_sms_opt_out_phone_number', table_name='sms_opt_out')
    op.drop_table('sms_opt_out')
    # Note: PostgreSQL cannot drop an enum value; 'skipped' is left in place.
```

- [ ] **Step 2: Verify the migration chain is linear (single head)**

Run: `.venv/bin/alembic heads`
Expected: a single head — `e4f5a6b7c8d9 (head)`

- [ ] **Step 3: Verify the model matches the migration (no pending autogen diff)**

If a database is reachable, run: `.venv/bin/alembic upgrade head` then
`.venv/bin/alembic revision --autogenerate -m "check" --sql` and confirm it
produces no new `sms_opt_out` operations (then discard the throwaway revision).
If no database is reachable in this environment, state that and rely on the
test suite's `create_all` schema as the model/DDL cross-check.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/e4f5a6b7c8d9_add_sms_opt_out_and_skipped_status.py
git commit -m "feat(sms): migration for sms_opt_out table and skipped status"
```

---

## Final Verification

- [ ] Run the full suite: `.venv/bin/pytest -v`
- [ ] Expected: all tests pass, including the new opt-out, webhook, and worker tests.

## Self-Review Notes (author)

- **Spec coverage:** model (T1), repository (T1), webhook STOP/START (T2), worker send-time enforcement (T3), `skipped` status + migration (T3/T4), tests for all three layers (T1–T3) — all spec sections mapped.
- **Type consistency:** `SMSOptOutRepository.opt_out/opt_in/is_opted_out`, `PickupEventRepository.mark_sms_skipped`, and `SMSJobStatus.skipped` are used identically across tasks.
- **Phone matching:** exact string, per spec.
```
