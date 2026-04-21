# backend/app/routers/discs.py
import asyncio
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models.user import User
from app.repositories.disc import DiscRepository
from app.repositories.user import UserRepository
from app.schemas.disc import DiscOut, DiscCreate, DiscUpdate, DiscPage, DiscPhotoOut
from app.services.storage import upload_photo, delete_photo, get_public_url

router = APIRouter()


@router.get("", response_model=DiscPage, operation_id="listDiscs")
async def list_discs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    page_size: int = 50,
):
    repo = DiscRepository(db)
    if current_user.is_admin:
        discs = await repo.list_all(page=page, page_size=page_size)
        total = await repo.count_all()
    else:
        user_repo = UserRepository(db)
        phones = await user_repo.get_verified_numbers(current_user.id)
        numbers = [p.number for p in phones]
        discs = await repo.list_by_phones(numbers)
        total = await repo.count_by_phones(numbers)
    return DiscPage(
        items=[DiscOut.model_validate(d) for d in discs],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=DiscOut, status_code=201, operation_id="createDisc")
async def create_disc(
    body: DiscCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = DiscRepository(db)
    disc = await repo.create(**body.model_dump())
    await db.commit()
    disc = await repo.get_by_id(disc.id)
    return disc


@router.patch("/{disc_id}", response_model=DiscOut, operation_id="updateDisc")
async def update_disc(
    disc_id: uuid.UUID,
    body: DiscUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = DiscRepository(db)
    disc = await repo.get_by_id(disc_id)
    if disc is None:
        raise HTTPException(status_code=404, detail="Disc not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=422, detail="No fields provided for update")
    await repo.update(disc, **updates)
    await db.commit()
    disc = await repo.get_by_id(disc_id)
    return disc


@router.delete("/{disc_id}", status_code=204, operation_id="deleteDisc")
async def delete_disc(
    disc_id: uuid.UUID,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = DiscRepository(db)
    disc = await repo.get_by_id(disc_id)
    if disc is None:
        raise HTTPException(status_code=404, detail="Disc not found")
    await repo.delete(disc_id)
    await db.commit()


@router.post("/{disc_id}/photos", response_model=DiscPhotoOut, status_code=201, operation_id="uploadDiscPhoto")
async def upload_disc_photo(
    disc_id: uuid.UUID,
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = DiscRepository(db)
    disc = await repo.get_by_id(disc_id)
    if disc is None:
        raise HTTPException(status_code=404, detail="Disc not found")

    file_bytes = await file.read()
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    path = f"discs/{disc_id}/{uuid.uuid4()}.{ext}"
    sort_order = len(disc.photos)
    await asyncio.to_thread(upload_photo, file_bytes, path, file.content_type or "image/jpeg")
    photo = await repo.add_photo(disc_id, path, sort_order)
    await db.commit()
    return photo


@router.delete("/{disc_id}/photos/{photo_id}", status_code=204, operation_id="deleteDiscPhoto")
async def delete_disc_photo(
    disc_id: uuid.UUID,
    photo_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = DiscRepository(db)
    path = await repo.delete_photo(photo_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    await asyncio.to_thread(delete_photo, path)
    await db.commit()
