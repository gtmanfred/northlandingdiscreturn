# backend/tests/test_worker.py
import httpx
import pytest
from app.repositories.pickup_event import PickupEventRepository
from app.models.pickup_event import SMSJobStatus
from app.config import settings
from worker import main as worker_main

_RealAsyncClient = httpx.AsyncClient


def _expected_url() -> str:
    return f"{settings.SURGE_API_URL}/accounts/{settings.SURGE_ACCOUNT_ID}/messages"


def _make_async_client_factory(transport: httpx.MockTransport):
    def factory(*args, **kwargs):
        return _RealAsyncClient(transport=transport)
    return factory


async def test_process_sms_jobs_sends_and_marks_sent(db, monkeypatch):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15551234567", message="Test notice")
    await db.commit()

    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append({
            "url": str(request.url),
            "auth": request.headers.get("Authorization"),
            "json": httpx.Response(200, content=request.content).json(),
        })
        return httpx.Response(201, json={"id": "msg_test"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", _make_async_client_factory(transport))

    await worker_main.process_sms_jobs(db)

    assert len(captured) == 1
    assert captured[0]["url"] == _expected_url()
    assert captured[0]["auth"] == f"Bearer {settings.SURGE_API_KEY}"
    assert captured[0]["json"] == {
        "to": "+15551234567",
        "from": settings.SURGE_FROM_NUMBER,
        "body": "Test notice",
    }

    await db.refresh(job)
    assert job.status == SMSJobStatus.sent


async def test_process_sms_jobs_marks_failed_on_surge_error(db, monkeypatch):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15559999999", message="Another notice")
    await db.commit()

    transport = httpx.MockTransport(
        lambda r: httpx.Response(500, json={"error": {"type": "internal", "message": "boom"}})
    )
    monkeypatch.setattr(httpx, "AsyncClient", _make_async_client_factory(transport))

    await worker_main.process_sms_jobs(db)

    await db.refresh(job)
    assert job.status == SMSJobStatus.failed
    assert job.error  # populated from raise_for_status message
