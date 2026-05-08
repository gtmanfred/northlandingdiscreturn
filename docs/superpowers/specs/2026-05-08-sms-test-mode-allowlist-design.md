# SMS Test Mode Allowlist

**Date:** 2026-05-08
**Status:** Design

## Context

Outbound SMS flows through `app/services/surge.py` (`send_sms_sync` and `send_sms_async`). Both senders POST to Surge unconditionally for any caller (auth verification codes, notification service, heads-up worker, etc.).

When testing in non-production environments — staging, QA, dev pointed at a live Surge account — there is currently no way to prevent real SMS from going to real users. We want a flag that restricts outbound SMS to a specific set of phone numbers while leaving production behavior untouched.

## Goals

- Provide an explicit "test mode" toggle that, when enabled, only sends SMS to numbers on a configured allowlist.
- Silently drop (with a log line) any send to a non-allowlisted number while in test mode.
- Keep production unchanged: when test mode is off, every send goes through.
- Single chokepoint so no caller can bypass the gate by accident.

## Non-goals

- Inbound webhook gating (incoming SMS from Surge are not filtered).
- Admin UI toggle. Configuration is env-only.
- Per-message override or per-caller exceptions.
- Masking or redacting numbers in logs.
- Persisted record of dropped messages.

## Configuration

Two new settings in `app/config.py`:

```python
SMS_TEST_MODE = False              # bool, defaults to off (prod-safe)
SMS_ALLOWLIST: csv = ""            # CSV of E.164 numbers, coerced via existing csv helper
```

`figenv` coerces `SMS_TEST_MODE` from the env string to bool. `SMS_ALLOWLIST` reuses the `csv` coercer already used by `ADMIN_EMAILS`, producing a `list[str]` (empty list when unset).

Numbers in `SMS_ALLOWLIST` must be E.164 (`+15551234567`) — same format the senders already receive. No normalization is applied; the gate compares the caller-provided `to_number` against the list as-is.

## Enforcement

The gate lives inside `app/services/surge.py` so every caller — sync auth path, async worker, future callers — is covered without code changes elsewhere.

```python
import logging
logger = logging.getLogger(__name__)

def _allowed(to_number: str) -> bool:
    if not settings.SMS_TEST_MODE:
        return True
    if to_number in settings.SMS_ALLOWLIST:
        return True
    logger.info("sms blocked by test mode allowlist: to=%s", to_number)
    return False
```

Both senders short-circuit to a no-op when the gate denies:

```python
def send_sms_sync(to_number: str, body: str) -> None:
    if not _allowed(to_number):
        return
    # existing httpx POST

async def send_sms_async(client, to_number, body) -> None:
    if not _allowed(to_number):
        return
    # existing httpx POST
```

A blocked send returns `None` with no exception. The async worker treats no-exception as success and acks the job, so blocked messages do not retry forever.

## Logging

Stdlib `logging.getLogger(__name__)` (matches `app/main.py` precedent). One `INFO` line per blocked send including the full destination number. No structured `extra` payload — keeps parity with existing log calls in the codebase.

## Tests

`backend/tests/test_surge_service.py` adds six cases (three sync, three async):

- Test mode off → POST happens regardless of allowlist contents.
- Test mode on + number in allowlist → POST happens.
- Test mode on + number NOT in allowlist → no POST, log line captured via `caplog`.

Each test monkeypatches `settings.SMS_TEST_MODE` and `settings.SMS_ALLOWLIST` for isolation. The "blocked" tests assert the `httpx.MockTransport` handler is never invoked (e.g., set a flag in the handler that must remain `False`).

Existing tests keep passing because the default `SMS_TEST_MODE = False` makes `_allowed` a pass-through.

## Rollout

1. Merge with `SMS_TEST_MODE` defaulting to `False` everywhere.
2. In staging/dev fly apps, set `SMS_TEST_MODE=true` and `SMS_ALLOWLIST=+15551234567,...` via `fly secrets set`.
3. Production keeps the default — no change.

## Trade-offs

- **Single chokepoint vs. per-caller gating.** Gating in `surge.py` is harder to bypass and requires zero changes at call sites. The trade-off is that callers cannot opt out of the gate (e.g., to send a "your test was blocked" admin alert). Not needed today; can be added later if a use case appears.
- **Silent drop vs. raise.** Raising would surface accidental misconfiguration loudly but would also break the worker's retry semantics (it would re-queue blocked sends until they exceeded retry limits). Silent drop + log keeps the worker's contract intact at the cost of needing to read logs to confirm test-mode behavior.
- **Bool flag vs. allowlist-only semantic.** An explicit `SMS_TEST_MODE` toggle separates "filter is active" from "filter is configured." A single env var (empty list = pass-through) is simpler but ambiguous: a deploy that intended test mode but failed to set the allowlist would silently send everything. The two-var split makes that misconfiguration impossible.
