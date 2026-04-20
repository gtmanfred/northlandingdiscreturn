from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User, PhoneNumber
from app.repositories.user import UserRepository
from app.schemas.user import UserOut, PhoneNumberOut, AddPhoneRequest, VerifyPhoneRequest
from app.services.auth import generate_verification_code, send_verification_sms

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(User).where(User.id == current_user.id).options(selectinload(User.phone_numbers))
    )
    user = result.scalar_one()
    return user


@router.post("/me/phones", response_model=PhoneNumberOut)
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


@router.post("/me/phones/verify", response_model=PhoneNumberOut)
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


@router.delete("/me/phones/{number}", status_code=204)
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
