# backend/app/routers/discs.py
import asyncio
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models.user import User
from app.repositories.disc import DiscRepository
from app.repositories.owner import OwnerRepository
from app.repositories.user import UserRepository
from app.schemas.disc import DiscOut, DiscCreate, DiscUpdate, DiscPage, DiscPhotoOut
from app.services.heads_up import maybe_enqueue_heads_up
from app.config import settings
from app.services.storage import upload_photo, delete_photo, storage_path_to_url

router = APIRouter()


@router.get("", response_model=DiscPage, operation_id="listDiscs")
async def list_discs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    page_size: int = 50,
    is_found: bool | None = Query(default=None),
    is_returned: bool | None = Query(default=None),
    owner_name: str | None = Query(default=None),
):
    repo = DiscRepository(db)
    if current_user.is_admin:
        discs = await repo.list_all(
            page=page,
            page_size=page_size,
            is_found=is_found,
            is_returned=is_returned,
            owner_name=owner_name,
        )
        total = await repo.count_all(
            is_found=is_found,
            is_returned=is_returned,
            owner_name=owner_name,
        )
    else:
        user_repo = UserRepository(db)
        phones = await user_repo.get_verified_numbers(current_user.id)
        phone_strs = [p.number for p in phones]
        owner_ids = [o.id for o in await OwnerRepository(db).list_by_phones(phone_strs)]
        discs = await repo.list_by_owner_ids(owner_ids)
        total = await repo.count_by_owner_ids(owner_ids)
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
    owner_id = None
    owner_obj = None
    if body.owner_name and body.phone_number:
        owner_obj = await OwnerRepository(db).resolve_or_create(
            name=body.owner_name, phone_number=body.phone_number
        )
        owner_id = owner_obj.id

    disc = await repo.create(
        manufacturer=body.manufacturer,
        name=body.name,
        color=body.color,
        input_date=body.input_date,
        owner_id=owner_id,
        is_clear=body.is_clear,
        is_found=body.is_found,
    )

    if owner_obj is not None:
        await maybe_enqueue_heads_up(owner=owner_obj, is_found=disc.is_found, db=db)

    await db.commit()
    # Reload with owner + photos for the response
    return await repo.get_by_id(disc.id)


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

    payload = body.model_dump(exclude_unset=True)
    owner_name = payload.pop("owner_name", None)
    phone_number = payload.pop("phone_number", None)

    # Re-resolve owner if either field is present in the request
    if "owner_name" in body.model_fields_set or "phone_number" in body.model_fields_set:
        effective_name = owner_name if "owner_name" in body.model_fields_set else (
            disc.owner.name if disc.owner else None
        )
        effective_phone = phone_number if "phone_number" in body.model_fields_set else (
            disc.owner.phone_number if disc.owner else None
        )
        if effective_name and effective_phone:
            new_owner = await OwnerRepository(db).resolve_or_create(
                name=effective_name, phone_number=effective_phone
            )
            payload["owner_id"] = new_owner.id
        else:
            payload["owner_id"] = None

    if not payload:
        raise HTTPException(status_code=422, detail="No fields provided for update")

    await repo.update(disc, **payload)
    await db.commit()
    return await repo.get_by_id(disc_id)


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
    photo = await repo.add_photo(disc_id, storage_path_to_url(path), sort_order)
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
    stored = await repo.delete_photo(photo_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    marker = f"/{settings.SUPABASE_BUCKET}/"
    storage_path = stored.split(marker, 1)[-1] if marker in stored else stored
    await asyncio.to_thread(delete_photo, storage_path)
    await db.commit()
