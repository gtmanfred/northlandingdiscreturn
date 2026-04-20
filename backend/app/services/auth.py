import secrets
from datetime import datetime, timedelta, timezone
from jose import jwt
from twilio.rest import Client
from app.config import settings


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def generate_verification_code() -> str:
    return str(secrets.randbelow(900000) + 100000)


def send_verification_sms(to_number: str, code: str) -> None:
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    client.messages.create(
        body=f"Your North Landing disc return verification code is: {code}",
        from_=settings.TWILIO_FROM_NUMBER,
        to=to_number,
    )
