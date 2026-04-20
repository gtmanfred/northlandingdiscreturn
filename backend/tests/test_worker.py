# backend/tests/test_worker.py
from unittest.mock import MagicMock, patch
from app.repositories.pickup_event import PickupEventRepository
from app.models.pickup_event import SMSJobStatus
from app.config import settings
from worker.main import process_sms_jobs


async def test_process_sms_jobs_sends_and_marks_sent(db):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15551234567", message="Test notice")
    await db.commit()

    with patch("worker.main.Client") as MockClient:
        mock_messages = MagicMock()
        MockClient.return_value.messages = mock_messages
        await process_sms_jobs(db)

    mock_messages.create.assert_called_once_with(
        body="Test notice",
        from_=settings.TWILIO_FROM_NUMBER,
        to="+15551234567",
    )
    await db.refresh(job)
    assert job.status == SMSJobStatus.sent


async def test_process_sms_jobs_marks_failed_on_twilio_error(db):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15559999999", message="Another notice")
    await db.commit()

    with patch("worker.main.Client") as MockClient:
        MockClient.return_value.messages.create.side_effect = Exception("Twilio error")
        await process_sms_jobs(db)

    await db.refresh(job)
    assert job.status == SMSJobStatus.failed
    assert "Twilio error" in job.error
