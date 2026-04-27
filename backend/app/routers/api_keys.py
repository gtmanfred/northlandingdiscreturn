from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.repositories.api_key import ApiKeyRepository
from app.auth.api_key import generate_api_key

router = APIRouter()


class ApiKeyMeta(BaseModel):
    last_four: str
    created_at: datetime
    last_used_at: datetime | None = None


class ApiKeyCreated(BaseModel):
    api_key: str
    last_four: str
    created_at: datetime


@router.post("/me/api-key", status_code=status.HTTP_201_CREATED, response_model=ApiKeyCreated)
async def create_api_key(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyCreated:
    plaintext, key_hash, last_four = generate_api_key()
    repo = ApiKeyRepository(db)
    row = await repo.upsert_for_user(user.id, key_hash=key_hash, last_four=last_four)
    await db.commit()
    return ApiKeyCreated(api_key=plaintext, last_four=row.last_four, created_at=row.created_at)


@router.get("/me/api-key", response_model=ApiKeyMeta)
async def get_api_key(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyMeta:
    row = await ApiKeyRepository(db).get_for_user(user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No API key")
    return ApiKeyMeta(last_four=row.last_four, created_at=row.created_at, last_used_at=row.last_used_at)


@router.delete("/me/api-key", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    deleted = await ApiKeyRepository(db).delete_for_user(user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No API key")
    await db.commit()
