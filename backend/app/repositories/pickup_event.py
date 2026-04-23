# backend/app/repositories/pickup_event.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pickup_event import PickupEvent, DiscPickupNotification, SMSJob, SMSJobStatus


class PickupEventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_event(
        self, *, start_at: datetime, end_at: datetime, notes: str | None = None
    ) -> PickupEvent:
        event = PickupEvent(start_at=start_at, end_at=end_at, notes=notes)
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def get_event(self, event_id: uuid.UUID) -> PickupEvent | None:
        result = await self.db.execute(select(PickupEvent).where(PickupEvent.id == event_id))
        return result.scalar_one_or_none()

    async def list_events(self) -> list[PickupEvent]:
        result = await self.db.execute(
            select(PickupEvent).order_by(PickupEvent.start_at.desc())
        )
        return list(result.scalars().all())

    async def list_published_events(self) -> list[PickupEvent]:
        result = await self.db.execute(
            select(PickupEvent)
            .where(PickupEvent.notifications_sent_at.is_not(None))
            .order_by(PickupEvent.start_at.desc())
        )
        return list(result.scalars().all())

    async def update_event(self, event: PickupEvent, **kwargs) -> PickupEvent:
        bump_sequence = False
        for key, value in kwargs.items():
            current = getattr(event, key)
            if key in ("start_at", "end_at", "notes") and value != current:
                bump_sequence = True
            setattr(event, key, value)
        if bump_sequence:
            event.sequence = (event.sequence or 0) + 1
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def count_notifications_for_disc(self, disc_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(DiscPickupNotification).where(
                DiscPickupNotification.disc_id == disc_id
            )
        )
        return result.scalar_one()

    async def disc_already_notified_for_event(
        self, disc_id: uuid.UUID, pickup_event_id: uuid.UUID
    ) -> bool:
        result = await self.db.execute(
            select(DiscPickupNotification).where(
                DiscPickupNotification.disc_id == disc_id,
                DiscPickupNotification.pickup_event_id == pickup_event_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def create_disc_notification(
        self,
        *,
        disc_id: uuid.UUID,
        pickup_event_id: uuid.UUID,
        is_final_notice: bool = False,
    ) -> DiscPickupNotification:
        notif = DiscPickupNotification(
            disc_id=disc_id,
            pickup_event_id=pickup_event_id,
            is_final_notice=is_final_notice,
        )
        self.db.add(notif)
        await self.db.flush()
        await self.db.refresh(notif)
        return notif

    async def create_sms_job(self, *, phone_number: str, message: str) -> SMSJob:
        job = SMSJob(phone_number=phone_number, message=message)
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def claim_pending_sms_jobs(self, *, limit: int = 50) -> list[SMSJob]:
        """Select pending jobs, mark as processing, return them. Uses SKIP LOCKED."""
        result = await self.db.execute(
            select(SMSJob)
            .where(SMSJob.status == SMSJobStatus.pending)
            .order_by(SMSJob.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = list(result.scalars().all())
        for job in jobs:
            job.status = SMSJobStatus.processing
        await self.db.flush()
        return jobs

    async def mark_sms_sent(self, job: SMSJob) -> None:
        job.status = SMSJobStatus.sent
        job.processed_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def mark_sms_failed(self, job: SMSJob, error: str) -> None:
        job.status = SMSJobStatus.failed
        job.processed_at = datetime.now(timezone.utc)
        job.error = error
        await self.db.flush()
