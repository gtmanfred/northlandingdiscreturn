# Twilio → Surge SMS Migration

**Date:** 2026-05-07
**Status:** Design

## Context

The backend currently sends SMS through the Twilio Python SDK in two places — a synchronous verification-code send (`backend/app/services/auth.py`) and an async worker that drains a `SMSJob` queue every 10 seconds (`backend/worker/main.py`) — and accepts inbound replies on a Twilio-signed webhook at `POST /webhooks/twilio`. We are switching providers to Surge (`https://api.surge.app`).

Switching the provider is the only goal. The job-queue schema, scheduler cadence, verification UX, route mounting, and frontend stay untouched.

## Goals

- Send all outbound SMS via Surge.
- Validate inbound Surge webhooks correctly (HMAC-SHA256, replay protection).
- Remove the `twilio` dependency.
- Keep the call sites' shapes so existing tests (other than the Twilio mocks themselves) keep passing.

## Non-goals

- Job-queue schema changes.
- Multi-provider abstraction or feature-flag fallback to Twilio.
- Inbound STOP/HELP keyword handling (Surge handles compliance auto-replies; the existing handler also did not act on these).
- Migrating historical message records.

## Surge API contract

Verified from `docs.surge.app` on 2026-05-07.

**Send** — `POST https://api.surge.app/accounts/{account_id}/messages`
- Headers: `Authorization: Bearer <SURGE_API_KEY>`, `Content-Type: application/json`.
- Body (SimpleMessageParams): `{"to": "+1...", "from": "+1...", "body": "..."}`. `from` is optional (account default applies); we will send it explicitly so multi-number accounts behave deterministically.
- 201 returns `{"id": "...", ...}`. Non-2xx is treated as send failure.

**Inbound webhook signature**
- Header: `Surge-Signature: t=<unix-ts>,v1=<hex-hmac-sha256>`.
- Signed string: `f"{t}.".encode() + raw_request_body_bytes`. The raw body matters — re-serializing parsed JSON breaks the hash.
- Multiple `v1=` values may co-exist during signing-secret rotation; accept if any matches.
- Reject if `|now − t| > 300s`.

**Inbound event payload**
- JSON, top-level `type` (e.g. `"message.received"`).
- For inbound texts, the message body and contact phone live under `data.body` and `data.conversation.contact.phone_number`. The handler returns the parsed values; downstream consumers do not exist yet.

## Configuration

Replace the three `TWILIO_*` keys in `backend/app/config.py` with:

| Key | Purpose |
|---|---|
| `SURGE_API_KEY` | Bearer token for outbound sends. |
| `SURGE_ACCOUNT_ID` | Account scoping the URL path. |
| `SURGE_FROM_NUMBER` | Sender phone in E.164. Sent on every request. |
| `SURGE_WEBHOOK_SIGNING_SECRET` | HMAC key for inbound webhook validation. Distinct from `SURGE_API_KEY`. |
| `SURGE_API_URL` | Defaults to `https://api.surge.app`. Overridable so tests can target a mock transport. |

The same five keys propagate to `backend/.env.example`, `.env.example` (root), `docker-compose.yml`, `backend/teststack.toml`, `README.md`, and `docs/privacy-policy.md` (replacing the "Twilio" mention with "Surge").

Fly secrets are managed out-of-band. The PR description must call out: operator runs `fly secrets set SURGE_API_KEY=… SURGE_ACCOUNT_ID=… SURGE_FROM_NUMBER=… SURGE_WEBHOOK_SIGNING_SECRET=…`, unsets the old `TWILIO_*` secrets, and re-points the inbound webhook URL in the Surge dashboard at the new `/webhooks/sms` route.

## Architecture

### `app/services/surge.py` (new)

Single small module, two helpers, no class. Both call sites share one source of truth for URL composition, headers, and payload shape.

```python
def send_sms_sync(to_number: str, body: str) -> None: ...
async def send_sms_async(client: httpx.AsyncClient, to_number: str, body: str) -> None: ...
```

The async helper takes an externally-owned `AsyncClient` so the worker can amortize one client across a job batch. Both raise on non-2xx via `response.raise_for_status()`; they do not swallow errors. Timeout: 10s.

Rationale: keeping the helper free of business logic (no DB, no logging) makes it trivially unit-testable with `httpx.MockTransport` or `respx` and lets both call sites stay thin.

### `app/services/auth.py`

`send_verification_sms(to_number, code)` continues to exist with the same signature. Body becomes a one-line delegation to `surge.send_sms_sync`, with the verification text composed inline. The function name is preserved so `test_users.py`'s `patch("app.routers.users.send_verification_sms")` still binds.

### `worker/main.py`

`process_sms_jobs` opens one `httpx.AsyncClient` for the batch (`async with httpx.AsyncClient() as client:`) and calls `surge.send_sms_async(client, …)` per job inside the existing per-job try/except. The `functools.partial` + `loop.run_in_executor` shim disappears. Claim, mark-sent, mark-failed, scheduler cadence (`interval, seconds=10`), and logging all stay the same.

Failure semantics: any exception (transport error, `httpx.HTTPStatusError`) → `mark_sms_failed(job, str(e))` exactly as today.

### `app/routers/webhooks.py`

Rewrite around Surge's signing scheme. Public route becomes `POST /webhooks/sms` (`operation_id="surgeWebhook"`, `include_in_schema=False`). Whoever mounts the router must keep exactly one of {decorator path, include prefix} carrying the `/sms` segment so the public path is unambiguous.

Validation: parse the `Surge-Signature` header for `t` and one or more `v1`s, reject if either is missing or malformed; reject if `abs(time.time() - int(t)) > 300`; compute `hmac.new(secret, f"{t}.".encode() + raw_body, sha256).hexdigest()` and compare against each `v1` with `hmac.compare_digest`. Any failure → 403.

After validation: parse the JSON, branch on `type`. Only `"message.received"` is handled today (extract `data.body` + `data.conversation.contact.phone_number`); other types return `{"status": "ignored"}` with 200. This keeps Surge from retrying events we haven't wired up yet.

## Data flow

```
verification flow:        users router → BackgroundTask → send_verification_sms
                            → surge.send_sms_sync → POST api.surge.app/accounts/{id}/messages

queued bulk SMS:          repository writes SMSJob row → APScheduler tick (10s)
                            → process_sms_jobs claims batch → AsyncClient
                            → surge.send_sms_async per job → mark_sms_sent / mark_sms_failed

inbound reply:            Surge POST → /webhooks/sms
                            → validate Surge-Signature → parse → return parsed body+from
```

## Error handling

| Failure | Behavior |
|---|---|
| Surge 4xx/5xx on send | `raise_for_status()` → caller's `except` path. Worker marks job failed; verification raises into FastAPI's BackgroundTask (logged, does not 500 the user request since the verify endpoint already returned). |
| Network timeout | Same as above. 10s ceiling per request. |
| Webhook bad signature | 403, no body parsing. |
| Webhook stale timestamp (>5 min) | 403. |
| Webhook unknown event `type` | 200 `{"status": "ignored"}` so Surge does not retry. |
| Missing config (empty `SURGE_API_KEY`) | Send fails with `httpx.HTTPStatusError` (401 from Surge). No bespoke pre-check — same posture as today. |

## Testing

- `backend/tests/test_worker.py`: replace `patch("worker.main.Client")` with an `httpx.MockTransport` that intercepts `POST {SURGE_API_URL}/accounts/{account_id}/messages`. Inject the transport via the worker's `AsyncClient` (e.g. monkeypatch `httpx.AsyncClient` or pass through a fixture). Assert request JSON has `to`/`from`/`body`. Failure-path test: transport returns 500 → assert `mark_sms_failed` is called and the loop continues. Avoids adding `respx` as a dev dep (current `backend/pyproject.toml` `[project.optional-dependencies].dev` has only pytest deps).
- `backend/tests/test_webhooks.py`: replace `make_twilio_signature` with `make_surge_signature(raw_body, secret, ts)` returning `f"t={ts},v1={hmac_sha256_hex}"`. Cases: valid signature → 200; tampered `v1` → 403; stale `t` (>5 min) → 403; missing header → 403; unknown event `type` → 200 `ignored`.
- `backend/tests/test_users.py:131`: patch target stays `app.routers.users.send_verification_sms`. No edit needed.
- New: `backend/tests/test_surge_service.py` (small) covering `send_sms_sync`/`send_sms_async` payload shape and error propagation, using `httpx.MockTransport`.

## Dependencies

- Drop `twilio>=9.0` from `backend/pyproject.toml`. Run `uv lock` to regenerate `backend/uv.lock`.
- `httpx>=0.27` is already a direct dep — nothing to add for the production path.

## Risks and mitigations

- **Webhook signature mismatch from form-vs-JSON parsing.** Mitigation: validation reads `await request.body()` raw bytes before any parsing. Tests assert this with a known-good HMAC computed from the same bytes.
- **Surge dashboard webhook URL not updated at deploy time.** Mitigation: PR description checklist; route renamed so accidentally hitting the old `/webhooks/twilio` 404s loudly instead of silently appearing healthy.
- **Account-default `from` differs from intended sender on multi-number accounts.** Mitigation: always send `SURGE_FROM_NUMBER` explicitly in the payload.
- **`uv lock` regeneration drift.** Mitigation: regenerate in the same commit as the dep removal; CI lockfile check (if present) catches divergence.

## Out of scope (explicit)

- Storing inbound replies. The current handler echoes parsed values; downstream persistence is a future change.
- STOP/HELP keyword handling.
- Two-way conversation threading.
- Per-tenant Surge accounts.
