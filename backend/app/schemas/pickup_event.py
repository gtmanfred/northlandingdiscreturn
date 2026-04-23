# backend/app/schemas/pickup_event.py
import uuid
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, model_validator
from app.models.pickup_event import SMSJobStatus


class PickupEventOut(BaseModel):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    notes: str | None
    notifications_sent_at: datetime | None
    sequence: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PickupEventCreate(BaseModel):
    start_at: datetime
    end_at: datetime
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_window(self) -> "PickupEventCreate":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if self.start_at > datetime.now(timezone.utc) + timedelta(days=365):
            raise ValueError("start_at is too far in the future")
        return self


class PickupEventUpdate(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    notes: str | None = None


class NotifyResult(BaseModel):
    sms_jobs_enqueued: int
    discs_notified: int


class SMSJobOut(BaseModel):
    id: uuid.UUID
    phone_number: str
    status: SMSJobStatus
    created_at: datetime
    processed_at: datetime | None
    error: str | None

    model_config = {"from_attributes": True}
