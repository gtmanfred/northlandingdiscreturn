import uuid
from typing import Annotated
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User, PhoneNumber
from app.repositories.user import UserRepository
from app.repositories.disc import DiscRepository
from app.schemas.user import UserOut, PhoneNumberOut, AddPhoneRequest, VerifyPhoneRequest
from app.schemas.disc import DiscOut, WishlistDiscCreate
from app.services.auth import generate_verification_code, send_verification_sms

router = APIRouter()


@router.get("/me", response_model=UserOut, operation_id="getMe")
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(User).where(User.id == current_user.id).options(selectinload(User.phone_numbers))
    )
    user = result.scalar_one()
    return user


@router.post("/me/phones", response_model=PhoneNumberOut, operation_id="addPhone")
async def add_phone(
    body: AddPhoneRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = UserRepository(db)
    existing = await repo.get_phone_by_number(current_user.id, body.number)
    if existing and existing.verified:
        raise HTTPException(status_code=400, detail="Phone number already verified")
    if existing is None:
        phone = await repo.add_phone_number(current_user.id, body.number)
    else:
        phone = existing
    code = generate_verification_code()
    await repo.set_verification_code(phone.id, code)
    await db.commit()
    background_tasks.add_task(send_verification_sms, body.number, code)
    await db.refresh(phone)
    return phone


@router.post("/me/phones/verify", response_model=PhoneNumberOut, operation_id="verifyPhone")
async def verify_phone(
    body: VerifyPhoneRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = UserRepository(db)
    phone = await repo.get_phone_by_number(current_user.id, body.number)
    if phone is None:
        raise HTTPException(status_code=404, detail="Phone number not found")
    if phone.verified:
        raise HTTPException(status_code=400, detail="Phone number already verified")
    if not phone.verification_expires_at or phone.verification_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification code expired")
    if phone.verification_code != body.code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    phone = await repo.verify_phone(phone.id)
    await db.commit()
    return phone


@router.delete("/me/phones/{number}", status_code=204, operation_id="removePhone")
async def remove_phone(
    number: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = UserRepository(db)
    phone = await repo.get_phone_by_number(current_user.id, number)
    if phone is None:
        raise HTTPException(status_code=404, detail="Phone number not found")
    await repo.delete_phone(phone.id)
    await db.commit()


@router.get("/me/wishlist", response_model=list[DiscOut], operation_id="getMyWishlist")
async def get_my_wishlist(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user_repo = UserRepository(db)
    phones = await user_repo.get_verified_numbers(current_user.id)
    numbers = [p.number for p in phones]
    if not numbers:
        return []
    disc_repo = DiscRepository(db)
    return await disc_repo.list_wishlist_by_phones(numbers)


@router.get("/me/discs", response_model=list[DiscOut], operation_id="getMyDiscs")
async def get_my_discs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user_repo = UserRepository(db)
    phones = await user_repo.get_verified_numbers(current_user.id)
    numbers = [p.number for p in phones]
    if not numbers:
        return []
    disc_repo = DiscRepository(db)
    return await disc_repo.list_found_by_phones(numbers)


@router.post("/me/wishlist", response_model=DiscOut, status_code=201, operation_id="addWishlistDisc")
async def add_wishlist_disc(
    body: WishlistDiscCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user_repo = UserRepository(db)
    phones = await user_repo.get_verified_numbers(current_user.id)
    verified_numbers = {p.number for p in phones}
    if not verified_numbers:
        raise HTTPException(status_code=400, detail="No verified phone number on account")
    if body.phone_number not in verified_numbers:
        raise HTTPException(status_code=400, detail="Phone number not verified on your account")
    disc_repo = DiscRepository(db)
    disc = await disc_repo.create(
        manufacturer=body.manufacturer or "Unknown",
        name=body.name or "Unknown",
        color=body.color or "Unknown",
        input_date=date.today(),
        phone_number=body.phone_number,
        owner_name=body.owner_name or current_user.name,
        is_found=False,
    )
    await db.commit()
    return await disc_repo.get_by_id(disc.id)


@router.delete("/me/wishlist/{disc_id}", status_code=204, operation_id="removeWishlistDisc")
async def remove_wishlist_disc(
    disc_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user_repo = UserRepository(db)
    phones = await user_repo.get_verified_numbers(current_user.id)
    numbers = [p.number for p in phones]
    disc_repo = DiscRepository(db)
    disc = await disc_repo.get_by_id(disc_id)
    if disc is None or disc.is_found or disc.phone_number not in numbers:
        raise HTTPException(status_code=404, detail="Wishlist disc not found")
    await disc_repo.delete(disc_id)
    await db.commit()
