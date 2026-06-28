# SMS STOP/START Opt-Out — Design

**Date:** 2026-06-28
**Status:** Approved (pending spec review)

## Problem

Recipients can reply `STOP` to opt out of SMS and `START` to opt back in. We
must record opt-out state and never send SMS to an opted-out number until they
opt back in. Inbound SMS already arrives via the Surge webhook
(`POST /webhooks/sms`), which currently validates the signature, parses
`message.received`, and no-ops on the body.

## Decisions

- **Storage:** dedicated `sms_opt_out` table keyed on `phone_number` (decoupled
  from `Owner`; covers shared/unlinked numbers; single source of truth).
- **Enforcement:** at worker send-time only (single safety net catching every
  enqueue path, including jobs queued before the opt-out arrived).
- **Keywords:** exactly `STOP` / `START` (trimmed, case-insensitive — webhook
  already uppercases the body).
- **Confirmation reply:** none.
- **Skipped jobs:** new `skipped` value on `SMSJobStatus`.

## Architecture

### 1. Model — `app/models/sms_opt_out.py`

```python
class SMSOptOut(Base):
    __tablename__ = "sms_opt_out"
    id: Mapped[uuid.UUID]          # pk, default uuid4
    phone_number: Mapped[str]      # String, unique=True, index=True, nullable=False
    opted_out_at: Mapped[datetime] # DateTime(tz=True), server_default=func.now()
```

Row present = opted out. STOP upserts (idempotent), START deletes (idempotent).
Register in `app/models/__init__.py`.

### 2. SMSJobStatus — add `skipped`

`app/models/pickup_event.py`: add `skipped = "skipped"` to the enum.

Native PG enum `smsjobstatus` requires `ALTER TYPE smsjobstatus ADD VALUE
IF NOT EXISTS 'skipped'`. `ADD VALUE` cannot run inside a transaction block, so
the migration must run it in an autocommit block:

```python
def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE smsjobstatus ADD VALUE IF NOT EXISTS 'skipped'")
```

`downgrade` is a no-op (PG cannot drop an enum value cleanly); document this.

### 3. Repository — `app/repositories/sms_opt_out.py`

```python
class SMSOptOutRepository:
    def __init__(self, db: AsyncSession): ...
    async def opt_out(self, phone_number: str) -> None      # insert if absent
    async def opt_in(self, phone_number: str) -> None       # delete if present
    async def is_opted_out(self, phone_number: str) -> bool
```

`opt_out` guards on existence (or `ON CONFLICT DO NOTHING`) so duplicate STOPs
are safe. `opt_in` deletes the row if present; a START from a never-opted-out
number is a no-op.

### 4. Webhook — `app/routers/webhooks.py`

`surge_inbound` gains `db: AsyncSession = Depends(get_db)`. After signature
validation and `message.received` parsing:

```
body == "STOP"  -> repo.opt_out(from_number)
body == "START" -> repo.opt_in(from_number)
else            -> no-op
```

Skip the keyword action when `from_number` is empty. Signature validation,
403 path, and `ignored` response for other event types are unchanged. No
confirmation SMS sent.

### 5. Enforcement — `worker/main.py`

In `process_sms_jobs`, before calling `send_sms_async` for each claimed job:

```
if await opt_out_repo.is_opted_out(job.phone_number):
    job -> mark skipped (status=skipped, processed_at=now)
    continue   # do not send
```

Add `mark_sms_skipped(job)` to `PickupEventRepository` (mirrors
`mark_sms_sent`). The opt-out check happens after the job is claimed, so
ordering vs. claim does not matter — the safety net is the send gate.

## Data Flow

```
Inbound STOP/START
  Surge -> POST /webhooks/sms -> validate sig -> parse message.received
        -> STOP: opt_out(phone)  |  START: opt_in(phone)

Outbound SMS
  enqueue (welcome / heads-up / pickup notify) -> sms_jobs (pending)
  worker claims pending -> is_opted_out(phone)?
        yes -> mark skipped
        no  -> send_sms_async -> mark sent / failed
```

## Error Handling

- Duplicate STOP / repeated START: idempotent (existence guard / delete-if-present).
- START from never-opted-out number: no-op.
- Empty `from_number` in webhook: skip keyword action, still return 200.
- Opt-out lookup failure in worker: exception path already marks job `failed`;
  the job stays out of `sent`, so no message leaks. (Lookup is a simple SELECT;
  failure is unexpected.)
- Phone-number format: opt-out stores the exact `phone_number` Surge sends on
  inbound; jobs store the number we send to. Both are expected E.164 from Surge.
  Exact string match is used. **Risk:** if outbound and inbound formats ever
  differ, enforcement could miss — acceptable for now; revisit if Surge proves
  inconsistent.

## Testing (pytest + pytest-asyncio, asyncio_mode=auto)

`tests/test_webhooks.py` (extend):
- Valid signed `STOP` creates an opt-out row for the sender.
- Valid signed `START` removes an existing opt-out row.
- Duplicate `STOP` is idempotent (one row).
- `START` with no existing row is a no-op (no error).
- Non-keyword body leaves opt-out state unchanged.
- Empty `from_number` does not error.

`tests/test_worker.py` (extend):
- Job for an opted-out number is marked `skipped` and no HTTP call is made
  (assert via the httpx MockTransport — handler not invoked).
- Job for a non-opted-out number sends normally (existing behavior intact).

New `tests/test_sms_opt_out.py` (repository unit tests):
- `opt_out` then `is_opted_out` -> True; `opt_in` -> `is_opted_out` False.
- `opt_out` twice -> single row.

## Out of Scope (YAGNI)

- Confirmation/auto-reply SMS.
- Extended keyword set (UNSUBSCRIBE, CANCEL, YES, etc.).
- Enqueue-time pre-filtering (worker send-time is the single enforcement point).
- Admin UI / surfacing opt-out state in the API.
- Per-owner opt-out flag.
```
