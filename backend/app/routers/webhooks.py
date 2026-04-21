# backend/app/routers/webhooks.py
import hmac
import hashlib
import base64
from fastapi import APIRouter, Request, HTTPException
from app.config import settings

router = APIRouter()


def validate_twilio_signature(request_url: str, params: dict, signature: str) -> bool:
    s = request_url
    for key in sorted(params.keys()):
        s += key + params[key]
    mac = hmac.new(settings.TWILIO_AUTH_TOKEN.encode(), s.encode(), hashlib.sha1)
    expected = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(expected, signature)


@router.post("/twilio", operation_id="twilioWebhook", include_in_schema=False)
async def twilio_inbound(request: Request):
    form = await request.form()
    params = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)

    if not validate_twilio_signature(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    body = params.get("Body", "").strip().upper()
    from_number = params.get("From", "")
    return {"status": "received", "from": from_number, "body": body}
