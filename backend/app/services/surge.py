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
