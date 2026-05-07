# backend/tests/test_surge_service.py
import httpx
import pytest
from app.config import settings
from app.services import surge


def _expected_url() -> str:
    return f"{settings.SURGE_API_URL}/accounts/{settings.SURGE_ACCOUNT_ID}/messages"


def test_send_sms_sync_posts_expected_payload(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(surge, "_make_sync_client", lambda: httpx.Client(transport=transport))

    surge.send_sms_sync("+15551234567", "hello")

    assert captured["url"] == _expected_url()
    assert captured["auth"] == f"Bearer {settings.SURGE_API_KEY}"
    assert captured["json"] == {
        "to": "+15551234567",
        "from": settings.SURGE_FROM_NUMBER,
        "body": "hello",
    }


def test_send_sms_sync_raises_on_non_2xx(monkeypatch):
    transport = httpx.MockTransport(lambda r: httpx.Response(500, json={"error": {"type": "x"}}))
    monkeypatch.setattr(surge, "_make_sync_client", lambda: httpx.Client(transport=transport))
    with pytest.raises(httpx.HTTPStatusError):
        surge.send_sms_sync("+15551234567", "hello")


async def test_send_sms_async_posts_expected_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await surge.send_sms_async(client, "+15559999999", "world")

    assert captured["url"] == _expected_url()
    assert captured["json"]["to"] == "+15559999999"
    assert captured["json"]["body"] == "world"


async def test_send_sms_async_raises_on_non_2xx():
    transport = httpx.MockTransport(lambda r: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await surge.send_sms_async(client, "+15550000000", "x")
