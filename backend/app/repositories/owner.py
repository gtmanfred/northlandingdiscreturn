import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.owner import Owner


class OwnerRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_or_create(self, *, name: str, phone_number: str) -> Owner:
        result = await self.db.execute(
            select(Owner).where(
                Owner.name == name,
                Owner.phone_number == phone_number,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        owner = Owner(name=name, phone_number=phone_number)
        self.db.add(owner)
        await self.db.flush()
        await self.db.refresh(owner)
        return owner

    async def get_by_id(self, owner_id: uuid.UUID) -> Owner | None:
        result = await self.db.execute(select(Owner).where(Owner.id == owner_id))
        return result.scalar_one_or_none()

    async def list_by_phones(self, phone_numbers: list[str]) -> list[Owner]:
        if not phone_numbers:
            return []
        result = await self.db.execute(
            select(Owner).where(Owner.phone_number.in_(phone_numbers))
        )
        return list(result.scalars().all())

    async def mark_heads_up_sent(self, owner: Owner) -> Owner:
        owner.heads_up_sent_at = func.now()
        await self.db.flush()
        await self.db.refresh(owner)
        return owner

    async def suggest_names(self, limit: int = 50) -> list[str]:
        result = await self.db.execute(
            select(Owner.name).distinct().order_by(func.lower(Owner.name)).limit(limit)
        )
        return [row[0] for row in result.all()]

    async def list_phones_for_name(self, name: str) -> list[str]:
        result = await self.db.execute(
            select(Owner.phone_number).where(Owner.name.ilike(name)).distinct()
        )
        return [row[0] for row in result.all()]
