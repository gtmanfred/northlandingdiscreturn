import secrets
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.services.surge import send_sms_sync
from app.config import settings


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def generate_verification_code() -> str:
    return str(secrets.randbelow(900000) + 100000)


def create_refresh_token() -> str:
    return secrets.token_hex(32)


def send_verification_sms(to_number: str, code: str) -> None:
    # Intentionally exempt from the SMS opt-out list: phone-verification OTP is
    # user-initiated transactional auth and is not subject to STOP opt-out (TCPA).
    send_sms_sync(
        to_number,
        f"Your North Landing disc return verification code is: {code}",
    )
