from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models.disc import Disc
from app.models.user import PhoneNumber, User

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


class PhoneSuggestion(BaseModel):
    number: str
    label: str


@router.get("/phone", response_model=list[PhoneSuggestion], operation_id="getPhoneSuggestions")
async def get_phone_suggestions(
    owner_name: Annotated[str, Query(min_length=1)],
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PhoneSuggestion]:
    # Verified numbers from registered users matching owner_name
    registered_result = await db.execute(
        select(PhoneNumber.number, User.name, User.email)
        .join(User, PhoneNumber.user_id == User.id)
        .where(User.name.ilike(owner_name))
        .where(PhoneNumber.verified.is_(True))
    )
    registered: dict[str, PhoneSuggestion] = {
        row.number: PhoneSuggestion(
            number=row.number,
            label=f"{row.number} — {row.name} ({row.email})",
        )
        for row in registered_result.all()
    }

    # Phone numbers from past disc records for this owner
    disc_result = await db.execute(
        select(distinct(Disc.phone_number))
        .where(Disc.owner_name.ilike(owner_name))
        .where(Disc.phone_number.is_not(None))
        .where(Disc.phone_number != "")
    )
    for (number,) in disc_result.all():
        if number not in registered:
            registered[number] = PhoneSuggestion(number=number, label=number)

    return list(registered.values())
