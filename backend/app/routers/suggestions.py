from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models.disc import Disc
from app.models.owner import Owner
from app.models.user import PhoneNumber, User
from app.repositories.owner import OwnerRepository

router = APIRouter()

SuggestionField = Literal[
    "manufacturer", "name", "color", "owner_first_name", "owner_last_name"
]


@router.get("", response_model=list[str], operation_id="getSuggestions")
async def get_suggestions(
    field: Annotated[SuggestionField, Query()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[str]:
    if field in ("owner_first_name", "owner_last_name"):
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin required")
        repo = OwnerRepository(db)
        if field == "owner_first_name":
            return await repo.suggest_first_names()
        return await repo.suggest_last_names()

    col = getattr(Disc, field)
    subq = (
        select(distinct(col).label("val"))
        .where(col.is_not(None))
        .where(col != "")
        .subquery()
    )
    result = await db.execute(select(subq.c.val).order_by(func.lower(subq.c.val)))
    return [row[0] for row in result.all()]


class PhoneSuggestion(BaseModel):
    number: str
    label: str


@router.get("/phone", response_model=list[PhoneSuggestion], operation_id="getPhoneSuggestions")
async def get_phone_suggestions(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    owner_first_name: Annotated[str, Query()] = "",
    owner_last_name: Annotated[str, Query()] = "",
) -> list[PhoneSuggestion]:
    if not owner_first_name and not owner_last_name:
        return []

    full_name = f"{owner_first_name} {owner_last_name}".strip()
    registered: dict[str, PhoneSuggestion] = {}

    if full_name:
        registered_result = await db.execute(
            select(PhoneNumber.number, User.name, User.email)
            .join(User, PhoneNumber.user_id == User.id)
            .where(User.name.ilike(full_name))
            .where(PhoneNumber.verified.is_(True))
        )
        registered = {
            row.number: PhoneSuggestion(
                number=row.number,
                label=f"{row.number} — {row.name} ({row.email})",
            )
            for row in registered_result.all()
        }

    owner_stmt = select(distinct(Owner.phone_number))
    if owner_first_name:
        owner_stmt = owner_stmt.where(Owner.first_name.ilike(owner_first_name))
    if owner_last_name:
        owner_stmt = owner_stmt.where(Owner.last_name.ilike(owner_last_name))
    owner_result = await db.execute(owner_stmt)
    for (number,) in owner_result.all():
        if number not in registered:
            registered[number] = PhoneSuggestion(number=number, label=number)

    return list(registered.values())
