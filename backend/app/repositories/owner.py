import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.owner import Owner


class OwnerRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_or_create(
        self, *, first_name: str, last_name: str, phone_number: str
    ) -> Owner:
        result = await self.db.execute(
            select(Owner).where(
                Owner.first_name == first_name,
                Owner.last_name == last_name,
                Owner.phone_number == phone_number,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        owner = Owner(
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
        )
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

    async def suggest_first_names(self, limit: int = 200) -> list[str]:
        result = await self.db.execute(
            select(Owner.first_name)
            .where(Owner.first_name != "")
            .distinct()
            .order_by(func.lower(Owner.first_name))
            .limit(limit)
        )
        return [row[0] for row in result.all()]

    async def suggest_last_names(self, limit: int = 200) -> list[str]:
        result = await self.db.execute(
            select(Owner.last_name)
            .where(Owner.last_name != "")
            .distinct()
            .order_by(func.lower(Owner.last_name))
            .limit(limit)
        )
        return [row[0] for row in result.all()]

    async def list_phones_for_name(
        self, *, first_name: str, last_name: str
    ) -> list[str]:
        """Phones for owners matching both prefixes (case-insensitive)."""
        stmt = select(Owner.phone_number).distinct()
        if first_name:
            stmt = stmt.where(Owner.first_name.ilike(first_name))
        if last_name:
            stmt = stmt.where(Owner.last_name.ilike(last_name))
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]
