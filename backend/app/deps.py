from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError
from app.database import get_db
from app.services.auth import decode_access_token
from app.repositories.user import UserRepository
from app.repositories.api_key import ApiKeyRepository
from app.auth.api_key import looks_like_api_key, hash_api_key
from app.models.user import User

bearer = HTTPBearer()


async def _user_from_api_key(token: str, db: AsyncSession) -> User | None:
    key_hash = hash_api_key(token)
    api_repo = ApiKeyRepository(db)
    row = await api_repo.get_by_hash(key_hash)
    if row is None:
        return None
    user = await UserRepository(db).get_by_id(row.user_id)
    if user is None:
        return None
    await api_repo.touch_last_used(row.id)
    await db.commit()
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    token = credentials.credentials

    if looks_like_api_key(token):
        user = await _user_from_api_key(token, db)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        return user

    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise JWTError("Missing sub claim")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user
