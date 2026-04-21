import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import AsyncSessionLocal
from app.repositories.user import UserRepository
from app.routers import auth, discs, users, admin, webhooks, suggestions
from app.services.storage import get_storage_client

logger = logging.getLogger(__name__)


async def _ensure_storage_bucket() -> None:
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        return

    def _create():
        client = get_storage_client()
        try:
            client.storage.create_bucket(settings.SUPABASE_BUCKET, options={"public": True})
        except Exception as e:
            logger.warning("Storage bucket creation skipped: %s", e)

    await asyncio.to_thread(_create)


async def _promote_seed_admins(db: AsyncSession) -> None:
    emails = settings.ADMIN_EMAILS
    if not emails:
        return
    repo = UserRepository(db)
    users = await repo.get_by_emails(emails)
    for user in users:
        if not user.is_admin:
            await repo.update(user, is_admin=True)
    await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _ensure_storage_bucket()
    async with AsyncSessionLocal() as db:
        await _promote_seed_admins(db)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="North Landing Disc Return", version="0.1.0", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(discs.router, prefix="/discs", tags=["discs"])
    app.include_router(users.router, prefix="/users", tags=["users"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
    app.include_router(suggestions.router, prefix="/suggestions", tags=["suggestions"])

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
