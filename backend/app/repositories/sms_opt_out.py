from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sms_opt_out import SMSOptOut


class SMSOptOutRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get(self, phone_number: str) -> SMSOptOut | None:
        result = await self.db.execute(
            select(SMSOptOut).where(SMSOptOut.phone_number == phone_number)
        )
        return result.scalar_one_or_none()

    async def is_opted_out(self, phone_number: str) -> bool:
        return await self._get(phone_number) is not None

    async def opt_out(self, phone_number: str) -> None:
        await self.db.execute(
            pg_insert(SMSOptOut)
            .values(phone_number=phone_number)
            .on_conflict_do_nothing(index_elements=["phone_number"])
        )
        await self.db.flush()

    async def opt_in(self, phone_number: str) -> None:
        existing = await self._get(phone_number)
        if existing is not None:
            await self.db.delete(existing)
            await self.db.flush()
