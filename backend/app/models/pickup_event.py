import enum
import uuid
from datetime import datetime, date
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class SMSJobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    sent = "sent"
    failed = "failed"


class PickupEvent(Base):
    __tablename__ = "pickup_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    notifications_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    disc_notifications: Mapped[list["DiscPickupNotification"]] = relationship(
        back_populates="pickup_event"
    )


class DiscPickupNotification(Base):
    __tablename__ = "disc_pickup_notifications"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    disc_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("discs.id"), nullable=False)
    pickup_event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pickup_events.id"), nullable=False
    )
    is_final_notice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    disc: Mapped["Disc"] = relationship(back_populates="pickup_notifications")
    pickup_event: Mapped["PickupEvent"] = relationship(back_populates="disc_notifications")


class SMSJob(Base):
    __tablename__ = "sms_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[SMSJobStatus] = mapped_column(
        Enum(SMSJobStatus, name="smsjobstatus"), default=SMSJobStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
