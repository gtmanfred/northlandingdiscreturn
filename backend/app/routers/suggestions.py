from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user
from app.models.disc import Disc
from app.models.user import User

router = APIRouter()

SuggestionField = Literal["manufacturer", "name", "color", "owner_name"]


@router.get("", response_model=list[str], operation_id="getSuggestions")
async def get_suggestions(
    field: Annotated[SuggestionField, Query()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[str]:
    if field == "owner_name" and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")
    col = getattr(Disc, field)
    subq = (
        select(distinct(col).label("val"))
        .where(col.is_not(None))
        .where(col != "")
        .subquery()
    )
    result = await db.execute(
        select(subq.c.val).order_by(func.lower(subq.c.val))
    )
    return [row[0] for row in result.all()]
