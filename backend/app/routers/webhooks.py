# backend/app/routers/webhooks.py
import hmac
import hashlib
import json
import time

from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories.sms_opt_out import SMSOptOutRepository

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
    if not secret:
        return False
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
    matches = [hmac.compare_digest(expected, v) for v in v1s]
    return any(matches)


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

    if from_number and body in ("STOP", "START"):
        opt_out_repo = SMSOptOutRepository(db)
        if body == "STOP":
            await opt_out_repo.opt_out(from_number)
        else:
            await opt_out_repo.opt_in(from_number)
        # get_db does not commit; persist the change before the session closes.
        await db.commit()

    return {"status": "received", "from": from_number, "body": body}
