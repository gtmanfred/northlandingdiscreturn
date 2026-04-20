# backend/worker/main.py
import asyncio
import logging
from twilio.rest import Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings
from app.repositories.pickup_event import PickupEventRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def process_sms_jobs(db: AsyncSession | None = None) -> None:
    close_after = db is None
    if db is None:
        db = SessionLocal()
    try:
        repo = PickupEventRepository(db)
        jobs = await repo.claim_pending_sms_jobs(limit=50)
        if not jobs:
            return
        logger.info(f"Processing {len(jobs)} SMS jobs")
        twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        for job in jobs:
            try:
                twilio_client.messages.create(
                    body=job.message,
                    from_=settings.TWILIO_FROM_NUMBER,
                    to=job.phone_number,
                )
                await repo.mark_sms_sent(job)
                logger.info(f"SMS sent to {job.phone_number}")
            except Exception as e:
                await repo.mark_sms_failed(job, str(e))
                logger.error(f"SMS failed to {job.phone_number}: {e}")
        await db.commit()
    finally:
        if close_after:
            await db.close()


async def main() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(process_sms_jobs, "interval", seconds=10, id="sms_worker")
    scheduler.start()
    logger.info("Worker started — polling for SMS jobs every 10 seconds")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
