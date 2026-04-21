# backend/app/schemas/pickup_event.py
import uuid
from datetime import datetime, date
from pydantic import BaseModel
from app.models.pickup_event import SMSJobStatus


class PickupEventOut(BaseModel):
    id: uuid.UUID
    scheduled_date: date
    notes: str | None
    notifications_sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PickupEventCreate(BaseModel):
    scheduled_date: date
    notes: str | None = None


class PickupEventUpdate(BaseModel):
    scheduled_date: date | None = None
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
