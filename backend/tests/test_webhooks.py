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


async def test_surge_webhook_rejects_when_signing_secret_unset(client, monkeypatch):
    monkeypatch.setenv("SURGE_WEBHOOK_SIGNING_SECRET", "")
    raw = _payload()
    ts = int(time.time())
    # Attacker computes HMAC with the (empty) secret they suspect is unset.
    sig = make_surge_signature(raw, "", ts)
    resp = await client.post(
        "/webhooks/sms",
        content=raw,
        headers={"Surge-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 403
