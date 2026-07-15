import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.import_staging import ImportStaging


class ImportStagingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_pending(
        self, *, created_by: uuid.UUID, filename: str | None, rows: list, plan: dict
    ) -> ImportStaging:
        # At most one active preview per admin: cancel their prior pending rows.
        await self.db.execute(
            update(ImportStaging)
            .where(
                ImportStaging.created_by == created_by,
                ImportStaging.status == "pending",
            )
            .values(status="canceled")
        )
        staging = ImportStaging(
            created_by=created_by,
            filename=filename,
            status="pending",
            rows=rows,
            plan=plan,
        )
        self.db.add(staging)
        await self.db.flush()
        await self.db.refresh(staging)
        return staging

    async def get(self, staging_id: uuid.UUID) -> ImportStaging | None:
        result = await self.db.execute(
            select(ImportStaging).where(ImportStaging.id == staging_id)
        )
        return result.scalar_one_or_none()

    async def set_status(self, staging: ImportStaging, status: str) -> ImportStaging:
        staging.status = status
        await self.db.flush()
        await self.db.refresh(staging)
        return staging
