# backend/app/routers/admin.py
import uuid
from datetime import date, datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import require_admin
from app.models.user import User
from app.repositories.user import UserRepository
from app.repositories.disc import DiscRepository
from app.repositories.pickup_event import PickupEventRepository
from app.schemas.user import UserOut, UpdateUserRequest
from app.schemas.disc import DiscOut, WishlistDiscCreate
from app.schemas.pickup_event import PickupEventOut, PickupEventCreate, PickupEventUpdate, NotifyResult
from app.services.notification import enqueue_pickup_notifications

router = APIRouter()


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = UserRepository(db)
    return await repo.list_all()


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    user = await repo.update(user, **updates)
    await db.commit()
    return user


@router.get("/users/{user_id}/wishlist", response_model=list[DiscOut])
async def get_user_wishlist(
    user_id: uuid.UUID,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    phones = await user_repo.get_verified_numbers(user_id)
    if not phones:
        return []
    disc_repo = DiscRepository(db)
    numbers = [p.number for p in phones]
    return await disc_repo.list_wishlist_by_phones(numbers)


@router.post("/users/{user_id}/wishlist", response_model=DiscOut, status_code=201)
async def add_user_wishlist(
    user_id: uuid.UUID,
    body: WishlistDiscCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    phones = await user_repo.get_verified_numbers(user_id)
    phone_number = phones[0].number if phones else None
    disc_repo = DiscRepository(db)
    disc = await disc_repo.create(
        manufacturer=body.manufacturer or "Unknown",
        name=body.name or "Unknown",
        color=body.color or "Unknown",
        input_date=date.today(),
        phone_number=phone_number,
        is_found=False,
    )
    await db.commit()
    return disc


@router.delete("/users/{user_id}/wishlist/{disc_id}", status_code=204)
async def remove_user_wishlist(
    user_id: uuid.UUID,
    disc_id: uuid.UUID,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = DiscRepository(db)
    disc = await repo.get_by_id(disc_id)
    if disc is None or disc.is_found:
        raise HTTPException(status_code=404, detail="Wishlist disc not found")
    await repo.delete(disc_id)
    await db.commit()


@router.get("/pickup-events", response_model=list[PickupEventOut])
async def list_pickup_events(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = PickupEventRepository(db)
    return await repo.list_events()


@router.post("/pickup-events", response_model=PickupEventOut, status_code=201)
async def create_pickup_event(
    body: PickupEventCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = PickupEventRepository(db)
    event = await repo.create_event(scheduled_date=body.scheduled_date, notes=body.notes)
    await db.commit()
    return event


@router.patch("/pickup-events/{event_id}", response_model=PickupEventOut)
async def update_pickup_event(
    event_id: uuid.UUID,
    body: PickupEventUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = PickupEventRepository(db)
    event = await repo.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Pickup event not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    event = await repo.update_event(event, **updates)
    await db.commit()
    return event


@router.post("/pickup-events/{event_id}/notify", response_model=NotifyResult)
async def notify_pickup_event(
    event_id: uuid.UUID,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = PickupEventRepository(db)
    event = await repo.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Pickup event not found")
    if event.notifications_sent_at is not None:
        raise HTTPException(status_code=400, detail="Notifications already sent for this event")

    sms_count, disc_count = await enqueue_pickup_notifications(event, db)
    await repo.update_event(event, notifications_sent_at=datetime.now(timezone.utc))
    await db.commit()
    return NotifyResult(sms_jobs_enqueued=sms_count, discs_notified=disc_count)
