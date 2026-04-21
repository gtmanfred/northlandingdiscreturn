from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.auth import create_access_token

router = APIRouter()

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


async def _maybe_promote_to_admin(
    user: User, email: str, repo: UserRepository, db: AsyncSession
) -> None:
    if email in settings.ADMIN_EMAILS and not user.is_admin:
        await repo.update(user, is_admin=True)
        await db.commit()


@router.get("/google", operation_id="googleLogin")
async def login_google(request: Request):
    redirect_uri = str(request.url_for("auth_google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="auth_google_callback", operation_id="googleCallback")
async def auth_google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(status_code=400, detail="Google auth failed")

    repo = UserRepository(db)
    user = await repo.get_by_google_id(user_info["sub"])
    if user is None:
        user = await repo.create(
            name=user_info.get("name", user_info["email"]),
            email=user_info["email"],
            google_id=user_info["sub"],
        )
        await db.commit()

    await _maybe_promote_to_admin(user, user_info["email"], repo, db)

    access_token = create_access_token(str(user.id))
    redirect_url = f"{settings.FRONTEND_URL}/auth/callback?token={access_token}"
    return RedirectResponse(url=redirect_url)


@router.post("/logout", operation_id="logout")
async def logout():
    return {"message": "logged out"}
