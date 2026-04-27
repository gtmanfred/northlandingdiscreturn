import hashlib
import hmac
import secrets
from app.config import settings

API_KEY_PREFIX = "hou_"


def generate_api_key() -> tuple[str, str, str]:
    plaintext = API_KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = hash_api_key(plaintext)
    last_four = plaintext[-4:]
    return plaintext, key_hash, last_four


def hash_api_key(plaintext: str) -> str:
    secret = settings.API_KEY_HMAC_SECRET
    if not secret:
        raise RuntimeError("API_KEY_HMAC_SECRET is not configured")
    return hmac.new(secret.encode("utf-8"), plaintext.encode("utf-8"), hashlib.sha256).hexdigest()


def looks_like_api_key(token: str) -> bool:
    return token.startswith(API_KEY_PREFIX)
