# backend/tests/test_webhooks.py
import hmac
import hashlib
import base64
from app.config import settings


def make_twilio_signature(url: str, params: dict, auth_token: str) -> str:
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    mac = hmac.new(auth_token.encode(), s.encode(), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


async def test_twilio_webhook_valid_signature(client):
    params = {"Body": "STOP", "From": "+15551234567"}
    url = "http://test/webhooks/twilio"
    sig = make_twilio_signature(url, params, settings.TWILIO_AUTH_TOKEN)
    resp = await client.post(
        "/webhooks/twilio",
        data=params,
        headers={"X-Twilio-Signature": sig},
    )
    assert resp.status_code == 200


async def test_twilio_webhook_invalid_signature(client):
    resp = await client.post(
        "/webhooks/twilio",
        data={"Body": "STOP", "From": "+15551234567"},
        headers={"X-Twilio-Signature": "bad-sig"},
    )
    assert resp.status_code == 403
