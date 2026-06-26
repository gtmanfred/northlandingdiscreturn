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

    if field == "color":
        # colors is an array column; surface distinct individual tags so chips
        # autocomplete on single colors, not whole combinations.
        tags = select(func.unnest(Disc.colors).label("val")).subquery()
        distinct_tags = (
            select(distinct(tags.c.val).label("val"))
            .where(tags.c.val.is_not(None))
            .where(tags.c.val != "")
            .subquery()
        )
        result = await db.execute(
            select(distinct_tags.c.val).order_by(func.lower(distinct_tags.c.val))
        )
        return [row[0] for row in result.all()]

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


class OwnerPhoneSuggestion(BaseModel):
    first_name: str
    last_name: str
    phone_number: str


@router.get(
    "/owners-by-phone",
    response_model=list[OwnerPhoneSuggestion],
    operation_id="getOwnersByPhone",
)
async def get_owners_by_phone(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    digits: Annotated[str, Query()] = "",
) -> list[OwnerPhoneSuggestion]:
    digits = "".join(ch for ch in digits if ch.isdigit())
    if len(digits) < 4:
        return []
    owners = await OwnerRepository(db).list_by_phone_suffix(digits)
    return [
        OwnerPhoneSuggestion(
            first_name=o.first_name,
            last_name=o.last_name,
            phone_number=o.phone_number,
        )
        for o in owners
    ]
