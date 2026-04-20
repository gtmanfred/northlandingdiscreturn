from sqlalchemy.ext.asyncio import AsyncSession


async def get_db() -> AsyncSession:
    raise NotImplementedError("database not yet configured")
