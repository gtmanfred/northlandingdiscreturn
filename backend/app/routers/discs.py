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
    if (
        body.owner_first_name is not None
        and body.owner_last_name is not None
        and body.phone_number
    ):
        owner_obj = await OwnerRepository(db).resolve_or_create(
            first_name=body.owner_first_name,
            last_name=body.owner_last_name,
            phone_number=body.phone_number,
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
        notes=body.notes,
    )

    if owner_obj is not None:
        await maybe_enqueue_heads_up(owner=owner_obj, is_found=disc.is_found, db=db)

    await db.commit()
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
    owner_first = payload.pop("owner_first_name", None)
    owner_last = payload.pop("owner_last_name", None)
    phone = payload.pop("phone_number", None)

    fields_set = body.model_fields_set
    owner_fields_touched = bool(
        fields_set & {"owner_first_name", "owner_last_name", "phone_number"}
    )
    if owner_fields_touched:
        cur = disc.owner
        eff_first = owner_first if "owner_first_name" in fields_set else (cur.first_name if cur else None)
        eff_last = owner_last if "owner_last_name" in fields_set else (cur.last_name if cur else None)
        eff_phone = phone if "phone_number" in fields_set else (cur.phone_number if cur else None)
        if eff_first is not None and eff_last is not None and eff_phone:
            new_owner = await OwnerRepository(db).resolve_or_create(
                first_name=eff_first,
                last_name=eff_last,
                phone_number=eff_phone,
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
