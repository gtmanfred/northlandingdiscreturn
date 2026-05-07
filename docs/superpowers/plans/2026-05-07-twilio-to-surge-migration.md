# Twilio → Surge SMS Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Swap the SMS provider from Twilio to Surge across the verification send path, the SMS-job worker, and the inbound webhook, without changing the job-queue schema or scheduler cadence.

**Architecture:** New `app/services/surge.py` owns Surge's `POST /accounts/{id}/messages` call shape with a sync helper for FastAPI's `BackgroundTask` flow and an async helper for the worker's `httpx.AsyncClient` batch loop. The webhook handler is rewritten around `Surge-Signature: t=…,v1=<HMAC-SHA256>` over `<t>.<raw-body>` with a 5-minute replay window. Env vars become `SURGE_API_KEY`, `SURGE_ACCOUNT_ID`, `SURGE_FROM_NUMBER`, `SURGE_WEBHOOK_SIGNING_SECRET`, plus an overridable `SURGE_API_URL` for tests.

**Tech Stack:** Python 3.12, FastAPI, `httpx>=0.27` (already a dep), APScheduler, SQLAlchemy async, pytest + pytest-asyncio, `httpx.MockTransport` for HTTP mocking (no new test deps).

**Spec:** `docs/superpowers/specs/2026-05-07-twilio-to-surge-migration-design.md`

---

## File structure

| File | Action | Responsibility |
|---|---|---|
| `backend/app/config.py` | modify | Replace `TWILIO_*` keys with `SURGE_*` keys + `SURGE_API_URL`. |
| `backend/app/services/surge.py` | create | Surge HTTP client: `send_sms_sync`, `send_sms_async`, shared URL/headers/payload. |
| `backend/app/services/auth.py` | modify | `send_verification_sms` delegates to `surge.send_sms_sync`. |
| `backend/worker/main.py` | modify | Replace Twilio Client + `run_in_executor` with `httpx.AsyncClient` + `surge.send_sms_async`. |
| `backend/app/routers/webhooks.py` | rewrite | Surge-Signature HMAC-SHA256 validation, route renamed `/sms`, JSON parsing. |
| `backend/tests/test_surge_service.py` | create | Unit tests for the Surge helpers. |
| `backend/tests/test_worker.py` | rewrite | Mock `httpx.AsyncClient` transport instead of Twilio Client. |
| `backend/tests/test_webhooks.py` | rewrite | `make_surge_signature` helper, valid/tampered/stale/missing/unknown-event cases. |
| `backend/pyproject.toml` | modify | Drop `twilio>=9.0`. |
| `backend/uv.lock` | regenerate | `uv lock`. |
| `backend/.env.example` | modify | Replace `TWILIO_*` block. |
| `.env.example` | modify | Replace `TWILIO_*` block. |
| `docker-compose.yml` | modify | Replace backend `TWILIO_*` env vars. |
| `backend/teststack.toml` | modify | Replace `TWILIO_*` test values. |
| `README.md` | modify | Update SMS section + env var table. |
| `docs/privacy-policy.md` | modify | "Twilio" → "Surge" on line 37. |

---

## Task 1: Replace Twilio config keys with Surge keys

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Edit config**

Replace the three `TWILIO_*` lines with five `SURGE_*` lines.

Open `backend/app/config.py`. Replace lines 15–17:
```python
    TWILIO_ACCOUNT_SID = ""
    TWILIO_AUTH_TOKEN = ""
    TWILIO_FROM_NUMBER = ""
```
with:
```python
    SURGE_API_KEY = ""
    SURGE_ACCOUNT_ID = ""
    SURGE_FROM_NUMBER = ""
    SURGE_WEBHOOK_SIGNING_SECRET = ""
    SURGE_API_URL = "https://api.surge.app"
```

- [ ] **Step 2: Sanity import**

Run: `cd backend && uv run python -c "from app.config import settings; print(settings.SURGE_API_URL)"`
Expected: `https://api.surge.app`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "config: replace TWILIO_* settings with SURGE_*"
```

---

## Task 2: Create the Surge service module (TDD)

**Files:**
- Create: `backend/app/services/surge.py`
- Create: `backend/tests/test_surge_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_surge_service.py`:
```python
# backend/tests/test_surge_service.py
import httpx
import pytest
from app.config import settings
from app.services import surge


def _expected_url() -> str:
    return f"{settings.SURGE_API_URL}/accounts/{settings.SURGE_ACCOUNT_ID}/messages"


def test_send_sms_sync_posts_expected_payload(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(surge, "_make_sync_client", lambda: httpx.Client(transport=transport))

    surge.send_sms_sync("+15551234567", "hello")

    assert captured["url"] == _expected_url()
    assert captured["auth"] == f"Bearer {settings.SURGE_API_KEY}"
    assert captured["json"] == {
        "to": "+15551234567",
        "from": settings.SURGE_FROM_NUMBER,
        "body": "hello",
    }


def test_send_sms_sync_raises_on_non_2xx(monkeypatch):
    transport = httpx.MockTransport(lambda r: httpx.Response(500, json={"error": {"type": "x"}}))
    monkeypatch.setattr(surge, "_make_sync_client", lambda: httpx.Client(transport=transport))
    with pytest.raises(httpx.HTTPStatusError):
        surge.send_sms_sync("+15551234567", "hello")


async def test_send_sms_async_posts_expected_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await surge.send_sms_async(client, "+15559999999", "world")

    assert captured["url"] == _expected_url()
    assert captured["json"]["to"] == "+15559999999"
    assert captured["json"]["body"] == "world"


async def test_send_sms_async_raises_on_non_2xx():
    transport = httpx.MockTransport(lambda r: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await surge.send_sms_async(client, "+15550000000", "x")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_surge_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.surge'`.

- [ ] **Step 3: Implement the module**

Create `backend/app/services/surge.py`:
```python
import httpx
from app.config import settings

SURGE_TIMEOUT = 10.0


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.SURGE_API_KEY}",
        "Content-Type": "application/json",
    }


def _url() -> str:
    return f"{settings.SURGE_API_URL}/accounts/{settings.SURGE_ACCOUNT_ID}/messages"


def _payload(to_number: str, body: str) -> dict:
    return {
        "to": to_number,
        "from": settings.SURGE_FROM_NUMBER,
        "body": body,
    }


def _make_sync_client() -> httpx.Client:
    return httpx.Client(timeout=SURGE_TIMEOUT)


def send_sms_sync(to_number: str, body: str) -> None:
    with _make_sync_client() as client:
        resp = client.post(_url(), json=_payload(to_number, body), headers=_headers())
        resp.raise_for_status()


async def send_sms_async(client: httpx.AsyncClient, to_number: str, body: str) -> None:
    resp = await client.post(
        _url(),
        json=_payload(to_number, body),
        headers=_headers(),
        timeout=SURGE_TIMEOUT,
    )
    resp.raise_for_status()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_surge_service.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/surge.py backend/tests/test_surge_service.py
git commit -m "feat(sms): add Surge HTTP client service with sync and async helpers"
```

---

## Task 3: Rewrite `send_verification_sms` to use Surge

**Files:**
- Modify: `backend/app/services/auth.py`

The existing `backend/tests/test_users.py` already patches `app.routers.users.send_verification_sms` by name (line 131); the patch target survives the rewrite, so no test edit is needed in this task.

- [ ] **Step 1: Replace the Twilio import + body**

Open `backend/app/services/auth.py`. Replace line 4:
```python
from twilio.rest import Client
```
with:
```python
from app.services.surge import send_sms_sync
```

Replace lines 26–32 (the `send_verification_sms` body):
```python
def send_verification_sms(to_number: str, code: str) -> None:
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    client.messages.create(
        body=f"Your North Landing disc return verification code is: {code}",
        from_=settings.TWILIO_FROM_NUMBER,
        to=to_number,
    )
```
with:
```python
def send_verification_sms(to_number: str, code: str) -> None:
    send_sms_sync(
        to_number,
        f"Your North Landing disc return verification code is: {code}",
    )
```

- [ ] **Step 2: Run the user tests to confirm patch target still binds**

Run: `cd backend && uv run pytest tests/test_users.py -v`
Expected: All passing.

- [ ] **Step 3: Verify nothing else imports `twilio` from auth.py**

Run: `cd backend && uv run python -c "import app.services.auth"`
Expected: No `ModuleNotFoundError` (twilio still installed at this point — Task 6 removes it).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/auth.py
git commit -m "feat(sms): route verification SMS through Surge service"
```

---

## Task 4: Rewrite the worker to use Surge (TDD)

**Files:**
- Modify: `backend/worker/main.py`
- Rewrite: `backend/tests/test_worker.py`

- [ ] **Step 1: Replace the worker tests**

Overwrite `backend/tests/test_worker.py` with:
```python
# backend/tests/test_worker.py
import httpx
import pytest
from app.repositories.pickup_event import PickupEventRepository
from app.models.pickup_event import SMSJobStatus
from app.config import settings
from worker import main as worker_main


def _expected_url() -> str:
    return f"{settings.SURGE_API_URL}/accounts/{settings.SURGE_ACCOUNT_ID}/messages"


def _make_async_client_factory(transport: httpx.MockTransport):
    def factory(*args, **kwargs):
        return httpx.AsyncClient(transport=transport)
    return factory


async def test_process_sms_jobs_sends_and_marks_sent(db, monkeypatch):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15551234567", message="Test notice")
    await db.commit()

    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append({
            "url": str(request.url),
            "auth": request.headers.get("Authorization"),
            "json": httpx.Response(200, content=request.content).json(),
        })
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", _make_async_client_factory(transport))

    await worker_main.process_sms_jobs(db)

    assert len(captured) == 1
    assert captured[0]["url"] == _expected_url()
    assert captured[0]["auth"] == f"Bearer {settings.SURGE_API_KEY}"
    assert captured[0]["json"] == {
        "to": "+15551234567",
        "from": settings.SURGE_FROM_NUMBER,
        "body": "Test notice",
    }

    await db.refresh(job)
    assert job.status == SMSJobStatus.sent


async def test_process_sms_jobs_marks_failed_on_surge_error(db, monkeypatch):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15559999999", message="Another notice")
    await db.commit()

    transport = httpx.MockTransport(
        lambda r: httpx.Response(500, json={"error": {"type": "internal", "message": "boom"}})
    )
    monkeypatch.setattr(httpx, "AsyncClient", _make_async_client_factory(transport))

    await worker_main.process_sms_jobs(db)

    await db.refresh(job)
    assert job.status == SMSJobStatus.failed
    assert job.error  # populated from raise_for_status message
```

- [ ] **Step 2: Run worker tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_worker.py -v`
Expected: FAIL — old worker still imports `twilio.rest.Client` and calls `client.messages.create`, so the assertion on the captured Surge URL never fires (the Surge URL is never hit).

- [ ] **Step 3: Rewrite the worker**

Overwrite `backend/worker/main.py` with:
```python
# backend/worker/main.py
import asyncio
import logging

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.repositories.pickup_event import PickupEventRepository
from app.services.surge import send_sms_async

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def process_sms_jobs(db: AsyncSession | None = None) -> None:
    close_after = db is None
    if db is None:
        db = SessionLocal()
    try:
        repo = PickupEventRepository(db)
        jobs = await repo.claim_pending_sms_jobs(limit=50)
        if not jobs:
            return
        logger.info(f"Processing {len(jobs)} SMS jobs")
        async with httpx.AsyncClient() as client:
            for job in jobs:
                try:
                    await send_sms_async(client, job.phone_number, job.message)
                    await repo.mark_sms_sent(job)
                    logger.info(f"SMS sent to {job.phone_number}")
                except Exception as e:
                    await repo.mark_sms_failed(job, str(e))
                    logger.error(f"SMS failed to {job.phone_number}: {e}")
        await db.commit()
    finally:
        if close_after:
            await db.close()


async def main() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(process_sms_jobs, "interval", seconds=10, id="sms_worker")
    scheduler.start()
    logger.info("Worker started — polling for SMS jobs every 10 seconds")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run worker tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_worker.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/worker/main.py backend/tests/test_worker.py
git commit -m "feat(worker): send queued SMS via Surge using httpx.AsyncClient"
```

---

## Task 5: Rewrite the inbound webhook for Surge (TDD)

**Files:**
- Rewrite: `backend/app/routers/webhooks.py`
- Rewrite: `backend/tests/test_webhooks.py`

The router is mounted at prefix `/webhooks` in `backend/app/main.py:70`. We change the in-router path from `/twilio` to `/sms` so the public route becomes `POST /webhooks/sms`.

- [ ] **Step 1: Replace the webhook tests**

Overwrite `backend/tests/test_webhooks.py` with:
```python
# backend/tests/test_webhooks.py
import hmac
import hashlib
import json
import time

from app.config import settings


def make_surge_signature(raw_body: bytes, secret: str, ts: int) -> str:
    signed = f"{ts}.".encode() + raw_body
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def _payload(body: str = "STOP", phone: str = "+15551234567") -> bytes:
    return json.dumps({
        "type": "message.received",
        "id": "evt_test",
        "data": {
            "body": body,
            "conversation": {"contact": {"phone_number": phone}},
        },
    }).encode()


async def test_surge_webhook_valid_signature(client):
    raw = _payload()
    ts = int(time.time())
    sig = make_surge_signature(raw, settings.SURGE_WEBHOOK_SIGNING_SECRET, ts)
    resp = await client.post(
        "/webhooks/sms",
        content=raw,
        headers={"Surge-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["from"] == "+15551234567"
    assert body["body"] == "STOP"


async def test_surge_webhook_invalid_signature(client):
    raw = _payload()
    ts = int(time.time())
    resp = await client.post(
        "/webhooks/sms",
        content=raw,
        headers={"Surge-Signature": f"t={ts},v1=deadbeef", "Content-Type": "application/json"},
    )
    assert resp.status_code == 403


async def test_surge_webhook_stale_timestamp(client):
    raw = _payload()
    ts = int(time.time()) - 600  # 10 minutes ago
    sig = make_surge_signature(raw, settings.SURGE_WEBHOOK_SIGNING_SECRET, ts)
    resp = await client.post(
        "/webhooks/sms",
        content=raw,
        headers={"Surge-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 403


async def test_surge_webhook_missing_signature_header(client):
    resp = await client.post(
        "/webhooks/sms",
        content=_payload(),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 403


async def test_surge_webhook_unknown_event_type(client):
    raw = json.dumps({"type": "message.delivered", "id": "evt_x", "data": {}}).encode()
    ts = int(time.time())
    sig = make_surge_signature(raw, settings.SURGE_WEBHOOK_SIGNING_SECRET, ts)
    resp = await client.post(
        "/webhooks/sms",
        content=raw,
        headers={"Surge-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}


async def test_surge_webhook_supports_multiple_v1_values(client):
    raw = _payload(body="HELP")
    ts = int(time.time())
    good = make_surge_signature(raw, settings.SURGE_WEBHOOK_SIGNING_SECRET, ts)
    # Append a second v1 with the matching value last.
    header = f"t={ts},v1=deadbeef,{good.split(',', 1)[1]}"
    resp = await client.post(
        "/webhooks/sms",
        content=raw,
        headers={"Surge-Signature": header, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_webhooks.py -v`
Expected: All fail — old route `/webhooks/twilio` still active, `/webhooks/sms` returns 404.

- [ ] **Step 3: Rewrite the router**

Overwrite `backend/app/routers/webhooks.py` with:
```python
# backend/app/routers/webhooks.py
import hmac
import hashlib
import json
import time

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

router = APIRouter()

SIGNATURE_TOLERANCE_SECONDS = 300


def _parse_signature_header(header: str) -> tuple[str | None, list[str]]:
    timestamp: str | None = None
    v1s: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            v1s.append(value)
    return timestamp, v1s


def validate_surge_signature(raw_body: bytes, header: str, secret: str) -> bool:
    timestamp, v1s = _parse_signature_header(header)
    if not timestamp or not v1s:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    signed = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, v) for v in v1s)


@router.post("/sms", operation_id="surgeWebhook", include_in_schema=False)
async def surge_inbound(request: Request):
    raw = await request.body()
    signature = request.headers.get("Surge-Signature", "")
    if not validate_surge_signature(raw, signature, settings.SURGE_WEBHOOK_SIGNING_SECRET):
        raise HTTPException(status_code=403, detail="Invalid Surge signature")

    payload = json.loads(raw or b"{}")
    if payload.get("type") != "message.received":
        return {"status": "ignored"}

    data = payload.get("data") or {}
    body = (data.get("body") or "").strip().upper()
    contact = (data.get("conversation") or {}).get("contact") or {}
    from_number = contact.get("phone_number", "")
    return {"status": "received", "from": from_number, "body": body}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_webhooks.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the full test suite**

Run: `cd backend && uv run pytest -v`
Expected: all green. (`twilio` is still installed at this point but no longer imported from app code.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/webhooks.py backend/tests/test_webhooks.py
git commit -m "feat(webhooks): replace Twilio inbound handler with Surge HMAC-SHA256 validator"
```

---

## Task 6: Drop the Twilio dependency

**Files:**
- Modify: `backend/pyproject.toml`
- Regenerate: `backend/uv.lock`

- [ ] **Step 1: Remove twilio from pyproject**

Open `backend/pyproject.toml`. Delete line 15:
```python
    "twilio>=9.0",
```

- [ ] **Step 2: Regenerate the lock file**

Run: `cd backend && uv lock`
Expected: lockfile updates, `twilio` and its transitives removed.

- [ ] **Step 3: Sync the venv**

Run: `cd backend && uv sync`
Expected: completes without error; `twilio` uninstalled.

- [ ] **Step 4: Confirm no source still imports twilio**

Run: `cd backend && uv run python -c "import worker.main; import app.services.auth; import app.routers.webhooks; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Run the full test suite again**

Run: `cd backend && uv run pytest -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "deps: drop twilio package after Surge migration"
```

---

## Task 7: Update env files, compose, README, and privacy doc

**Files:**
- Modify: `backend/.env.example`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `backend/teststack.toml`
- Modify: `README.md`
- Modify: `docs/privacy-policy.md`

- [ ] **Step 1: `backend/.env.example`**

Replace the three `TWILIO_*` lines (around lines 5–7) with:
```
SURGE_API_KEY=sk_live_replace-me
SURGE_ACCOUNT_ID=acct_replace-me
SURGE_FROM_NUMBER=+15550000000
SURGE_WEBHOOK_SIGNING_SECRET=replace-me
```

- [ ] **Step 2: Root `.env.example`**

Replace the three `TWILIO_*` lines (around lines 16–18) with:
```
# Surge SMS — leave blank to disable SMS notifications
SURGE_API_KEY=
SURGE_ACCOUNT_ID=
SURGE_FROM_NUMBER=
SURGE_WEBHOOK_SIGNING_SECRET=
```

- [ ] **Step 3: `docker-compose.yml`**

In the backend service env block (around lines 54–56), replace:
```yaml
      TWILIO_ACCOUNT_SID: ${TWILIO_ACCOUNT_SID:-}
      TWILIO_AUTH_TOKEN: ${TWILIO_AUTH_TOKEN:-}
      TWILIO_FROM_NUMBER: ${TWILIO_FROM_NUMBER:-}
```
with:
```yaml
      SURGE_API_KEY: ${SURGE_API_KEY:-}
      SURGE_ACCOUNT_ID: ${SURGE_ACCOUNT_ID:-}
      SURGE_FROM_NUMBER: ${SURGE_FROM_NUMBER:-}
      SURGE_WEBHOOK_SIGNING_SECRET: ${SURGE_WEBHOOK_SIGNING_SECRET:-}
```

If a worker service block is also present and references the same env vars, mirror the same change there.

- [ ] **Step 4: `backend/teststack.toml`**

Replace the three `TWILIO_*` lines (around lines 14–16) with:
```toml
SURGE_API_KEY = "test-key"
SURGE_ACCOUNT_ID = "acct_test"
SURGE_FROM_NUMBER = "+15550000000"
SURGE_WEBHOOK_SIGNING_SECRET = "test-secret"
SURGE_API_URL = "https://api.surge.app"
```

- [ ] **Step 5: `README.md`**

In the tech-stack table (line 17), change `SMS: Twilio (optional)` to `SMS: Surge (optional)`.

In the env-var table (around lines 89–91), replace the three `TWILIO_*` rows with rows for `SURGE_API_KEY`, `SURGE_ACCOUNT_ID`, `SURGE_FROM_NUMBER`, and `SURGE_WEBHOOK_SIGNING_SECRET`. Keep the "leave blank to disable SMS notifications" note.

- [ ] **Step 6: `docs/privacy-policy.md`**

On line 37, replace `Twilio — to deliver SMS messages and receive your replies.` with `Surge — to deliver SMS messages and receive your replies.`

- [ ] **Step 7: Sanity grep**

Run: `git grep -i twilio -- backend/ docker-compose.yml '*.env*' README.md docs/privacy-policy.md`
Expected: no matches.

(`docs/superpowers/specs/` and `docs/superpowers/plans/` historical files may still mention Twilio — leave them; they are dated design records.)

- [ ] **Step 8: Run the full test suite once more**

Run: `cd backend && uv run pytest -v`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add backend/.env.example .env.example docker-compose.yml backend/teststack.toml README.md docs/privacy-policy.md
git commit -m "config: rename Twilio env vars to Surge across env files and docs"
```

---

## Task 8: Manual end-to-end verification

This task is not automated. Run before opening the PR.

- [ ] **Step 1: Configure local Surge sandbox creds**

Set the four `SURGE_*` values in `backend/.env` (sandbox account credentials, sandbox phone, dev webhook signing secret).

- [ ] **Step 2: Boot the API and worker**

Run in two terminals:
```bash
cd backend && uv run uvicorn app.main:app --reload
cd backend && uv run python -m worker.main
```

- [ ] **Step 3: Verify the verification-code path**

In the frontend, add a phone number to a user; observe the SMS arrive on the test phone.

- [ ] **Step 4: Verify the queue worker path**

Trigger a pickup event that enqueues an `SMSJob` (or insert one directly via psql). Within ~10s, confirm worker logs `SMS sent to ...` and the row's status flips to `sent`.

- [ ] **Step 5: Verify the inbound webhook**

Point the Surge dashboard's inbound webhook at your dev URL (`https://<tunnel>/webhooks/sms`). Reply from the test phone. Confirm:
- Backend logs the parsed body and from-number, response 200.
- A request with a tampered signature returns 403.

- [ ] **Step 6: Compose smoke**

Run `docker-compose up backend` (with `.env` populated). Confirm the backend container starts and `/healthz` (or equivalent) responds.

- [ ] **Step 7: Open PR**

```bash
git push -u origin <branch>
GH_HOST=git.autodesk.com gh pr create --base main --title "Migrate SMS provider from Twilio to Surge" --body "$(cat <<'EOF'
## Summary
- Swap SMS provider from Twilio to Surge (api.surge.app)
- Replace `TWILIO_*` env vars with `SURGE_API_KEY`, `SURGE_ACCOUNT_ID`, `SURGE_FROM_NUMBER`, `SURGE_WEBHOOK_SIGNING_SECRET`
- Webhook route renamed `POST /webhooks/twilio` → `POST /webhooks/sms`, signature now HMAC-SHA256 over `<t>.<raw-body>`

## Operator checklist (must do at deploy)
- [ ] `fly secrets set SURGE_API_KEY=… SURGE_ACCOUNT_ID=… SURGE_FROM_NUMBER=… SURGE_WEBHOOK_SIGNING_SECRET=…`
- [ ] `fly secrets unset TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_FROM_NUMBER`
- [ ] Update inbound webhook URL in the Surge dashboard to `https://<host>/webhooks/sms`

## Test plan
- [ ] Verification code SMS delivers via Surge sandbox
- [ ] Worker drains an enqueued SMSJob and marks it sent
- [ ] Inbound webhook with valid signature returns 200; tampered/stale return 403
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** every section of the design doc maps to a task. Config (Task 1) → §Configuration. Surge service (Task 2) → §Architecture/`app/services/surge.py`. Auth send site (Task 3) → §`app/services/auth.py`. Worker (Task 4) → §`worker/main.py`. Webhook (Task 5) → §`app/routers/webhooks.py` + §Testing webhook cases. Dep removal (Task 6) → §Dependencies. Env/docs (Task 7) → §Configuration propagation. Manual verification (Task 8) → spec's risks (webhook URL update, multi-number from).
- **Placeholders:** none — all code blocks show full content, all expected outputs are concrete.
- **Type/name consistency:** `send_sms_sync` / `send_sms_async` are used identically in Tasks 2, 3, 4. `validate_surge_signature` named the same in handler and tests' implicit expectation. Env-var names are identical across all seven tasks. `SURGE_API_URL` referenced in tests (Task 2, Task 4) matches the config key added in Task 1.
