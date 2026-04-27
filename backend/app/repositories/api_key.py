import uuid
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from app.models.api_key import ApiKey


class ApiKeyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_for_user(
        self, user_id: uuid.UUID, *, key_hash: str, last_four: str
    ) -> ApiKey:
        await self.db.execute(delete(ApiKey).where(ApiKey.user_id == user_id))
        row = ApiKey(user_id=user_id, key_hash=key_hash, last_four=last_four)
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def get_for_user(self, user_id: uuid.UUID) -> ApiKey | None:
        result = await self.db.execute(select(ApiKey).where(ApiKey.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        result = await self.db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        return result.scalar_one_or_none()

    async def delete_for_user(self, user_id: uuid.UUID) -> bool:
        result = await self.db.execute(delete(ApiKey).where(ApiKey.user_id == user_id))
        return result.rowcount > 0

    async def touch_last_used(self, api_key_id: uuid.UUID) -> None:
        await self.db.execute(
            update(ApiKey).where(ApiKey.id == api_key_id).values(last_used_at=func.now())
        )
