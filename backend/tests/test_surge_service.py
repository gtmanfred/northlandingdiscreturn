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
        captured["auth"] = request.headers.get("Authorization")
        captured["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await surge.send_sms_async(client, "+15559999999", "world")

    assert captured["url"] == _expected_url()
    assert captured["auth"] == f"Bearer {settings.SURGE_API_KEY}"
    assert captured["json"]["to"] == "+15559999999"
    assert captured["json"]["body"] == "world"


async def test_send_sms_async_raises_on_non_2xx():
    transport = httpx.MockTransport(lambda r: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await surge.send_sms_async(client, "+15550000000", "x")


def _spy_sync_transport():
    state = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        state["called"] = True
        return httpx.Response(201, json={"id": "msg_test"})

    return httpx.MockTransport(handler), state


def test_send_sms_sync_blocked_when_test_mode_and_not_allowlisted(monkeypatch, caplog):
    monkeypatch.setenv("SMS_TEST_MODE", "true")
    monkeypatch.setenv("SMS_ALLOWLIST", "+15550000000")
    transport, state = _spy_sync_transport()
    monkeypatch.setattr(surge, "_make_sync_client", lambda: httpx.Client(transport=transport))

    with caplog.at_level("INFO", logger="app.services.surge"):
        surge.send_sms_sync("+15551234567", "hello")

    assert state["called"] is False
    assert any("sms blocked by test mode allowlist" in r.message for r in caplog.records)


def test_send_sms_sync_sent_when_test_mode_and_allowlisted(monkeypatch):
    monkeypatch.setenv("SMS_TEST_MODE", "true")
    monkeypatch.setenv("SMS_ALLOWLIST", "+15551234567")
    transport, state = _spy_sync_transport()
    monkeypatch.setattr(surge, "_make_sync_client", lambda: httpx.Client(transport=transport))

    surge.send_sms_sync("+15551234567", "hello")

    assert state["called"] is True


def test_send_sms_sync_sent_when_test_mode_off(monkeypatch):
    monkeypatch.delenv("SMS_TEST_MODE", raising=False)
    monkeypatch.delenv("SMS_ALLOWLIST", raising=False)
    transport, state = _spy_sync_transport()
    monkeypatch.setattr(surge, "_make_sync_client", lambda: httpx.Client(transport=transport))

    surge.send_sms_sync("+15551234567", "hello")

    assert state["called"] is True


async def test_send_sms_async_blocked_when_test_mode_and_not_allowlisted(monkeypatch, caplog):
    monkeypatch.setenv("SMS_TEST_MODE", "true")
    monkeypatch.setenv("SMS_ALLOWLIST", "+15550000000")
    state = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        state["called"] = True
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with caplog.at_level("INFO", logger="app.services.surge"):
            await surge.send_sms_async(client, "+15551234567", "hello")

    assert state["called"] is False
    assert any("sms blocked by test mode allowlist" in r.message for r in caplog.records)


async def test_send_sms_async_sent_when_test_mode_and_allowlisted(monkeypatch):
    monkeypatch.setenv("SMS_TEST_MODE", "true")
    monkeypatch.setenv("SMS_ALLOWLIST", "+15551234567")
    state = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        state["called"] = True
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await surge.send_sms_async(client, "+15551234567", "hello")

    assert state["called"] is True


async def test_send_sms_async_sent_when_test_mode_off(monkeypatch):
    monkeypatch.delenv("SMS_TEST_MODE", raising=False)
    monkeypatch.delenv("SMS_ALLOWLIST", raising=False)
    state = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        state["called"] = True
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await surge.send_sms_async(client, "+15551234567", "hello")

    assert state["called"] is True
