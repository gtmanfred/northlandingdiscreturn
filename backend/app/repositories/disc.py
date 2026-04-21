# backend/app/repositories/disc.py
import uuid
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.disc import Disc, DiscPhoto


class DiscRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        manufacturer: str,
        name: str,
        color: str,
        input_date: date,
        owner_name: str | None = None,
        phone_number: str | None = None,
        is_clear: bool = False,
        is_found: bool = True,
    ) -> Disc:
        disc = Disc(
            manufacturer=manufacturer,
            name=name,
            color=color,
            input_date=input_date,
            owner_name=owner_name,
            phone_number=phone_number,
            is_clear=is_clear,
            is_found=is_found,
        )
        self.db.add(disc)
        await self.db.flush()
        await self.db.refresh(disc)
        return disc

    async def get_by_id(self, disc_id: uuid.UUID) -> Disc | None:
        result = await self.db.execute(
            select(Disc).where(Disc.id == disc_id).options(selectinload(Disc.photos))
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        is_found: bool | None = None,
        is_returned: bool | None = None,
        owner_name: str | None = None,
    ) -> list[Disc]:
        offset = (page - 1) * page_size
        stmt = (
            select(Disc)
            .options(selectinload(Disc.photos))
            .order_by(Disc.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        if is_found is not None:
            stmt = stmt.where(Disc.is_found == is_found)
        if is_returned is not None:
            stmt = stmt.where(Disc.is_returned == is_returned)
        if owner_name is not None:
            stmt = stmt.where(Disc.owner_name.ilike(f"%{owner_name}%"))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_phone(self, phone_number: str) -> list[Disc]:
        result = await self.db.execute(
            select(Disc)
            .where(Disc.phone_number == phone_number, Disc.is_found == True)  # noqa: E712
            .options(selectinload(Disc.photos))
            .order_by(Disc.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_phones(self, phone_numbers: list[str]) -> list[Disc]:
        result = await self.db.execute(
            select(Disc)
            .where(Disc.phone_number.in_(phone_numbers), Disc.is_found == True)  # noqa: E712
            .options(selectinload(Disc.photos))
            .order_by(Disc.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_wishlist_by_phones(self, phone_numbers: list[str]) -> list[Disc]:
        result = await self.db.execute(
            select(Disc)
            .where(Disc.phone_number.in_(phone_numbers), Disc.is_found == False)  # noqa: E712
            .options(selectinload(Disc.photos))
            .order_by(Disc.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_found_by_phones(self, phone_numbers: list[str]) -> list[Disc]:
        result = await self.db.execute(
            select(Disc)
            .where(Disc.phone_number.in_(phone_numbers), Disc.is_found == True)  # noqa: E712
            .options(selectinload(Disc.photos))
            .order_by(Disc.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_all(
        self,
        *,
        is_found: bool | None = None,
        is_returned: bool | None = None,
        owner_name: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Disc)
        if is_found is not None:
            stmt = stmt.where(Disc.is_found == is_found)
        if is_returned is not None:
            stmt = stmt.where(Disc.is_returned == is_returned)
        if owner_name is not None:
            stmt = stmt.where(Disc.owner_name.ilike(f"%{owner_name}%"))
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def count_by_phones(self, phone_numbers: list[str]) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Disc).where(
                Disc.phone_number.in_(phone_numbers),
                Disc.is_found == True,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def list_unreturned_found(self) -> list[Disc]:
        """All found, unreturned discs with a phone number — for pickup notifications."""
        result = await self.db.execute(
            select(Disc).where(
                Disc.is_found == True,  # noqa: E712
                Disc.is_returned == False,  # noqa: E712
                Disc.phone_number.isnot(None),
            ).options(selectinload(Disc.photos))
        )
        return list(result.scalars().all())

    async def update(self, disc: Disc, **kwargs) -> Disc:
        for key, value in kwargs.items():
            setattr(disc, key, value)
        await self.db.flush()
        await self.db.refresh(disc)
        return disc

    async def delete(self, disc_id: uuid.UUID) -> None:
        result = await self.db.execute(select(Disc).where(Disc.id == disc_id))
        disc = result.scalar_one_or_none()
        if disc:
            await self.db.delete(disc)
            await self.db.flush()

    async def add_photo(self, disc_id: uuid.UUID, photo_path: str, sort_order: int = 0) -> DiscPhoto:
        photo = DiscPhoto(disc_id=disc_id, photo_path=photo_path, sort_order=sort_order)
        self.db.add(photo)
        await self.db.flush()
        await self.db.refresh(photo)
        return photo

    async def delete_photo(self, photo_id: uuid.UUID) -> str | None:
        """Returns the photo_path so the caller can delete from storage."""
        result = await self.db.execute(select(DiscPhoto).where(DiscPhoto.id == photo_id))
        photo = result.scalar_one_or_none()
        if photo:
            path = photo.photo_path
            await self.db.delete(photo)
            await self.db.flush()
            return path
        return None
