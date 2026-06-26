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
        colors: list[str],
        input_date: date,
        owner_id: uuid.UUID | None = None,
        is_clear: bool = False,
        is_found: bool = True,
        notes: str | None = None,
    ) -> Disc:
        disc = Disc(
            manufacturer=manufacturer,
            name=name,
            colors=colors,
            input_date=input_date,
            owner_id=owner_id,
            is_clear=is_clear,
            is_found=is_found,
            notes=notes,
        )
        self.db.add(disc)
        await self.db.flush()
        await self.db.refresh(disc)
        return disc

    async def get_by_id(self, disc_id: uuid.UUID) -> Disc | None:
        result = await self.db.execute(
            select(Disc)
            .where(Disc.id == disc_id)
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _apply_filters(stmt, *, is_found, is_returned, owner_name):
        from app.models.owner import Owner
        if owner_name is not None:
            stmt = stmt.join(Owner, Disc.owner_id == Owner.id).where(
                func.concat(Owner.first_name, " ", Owner.last_name).ilike(f"%{owner_name}%")
            )
        if is_found is not None:
            stmt = stmt.where(Disc.is_found == is_found)
        if is_returned is not None:
            stmt = stmt.where(Disc.is_returned == is_returned)
        return stmt

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
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
            .order_by(Disc.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        stmt = self._apply_filters(
            stmt, is_found=is_found, is_returned=is_returned, owner_name=owner_name
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_export(
        self, *, is_found=None, is_returned=None, owner_name=None
    ) -> list[Disc]:
        stmt = (
            select(Disc)
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
            .order_by(Disc.created_at.desc())
        )
        stmt = self._apply_filters(
            stmt, is_found=is_found, is_returned=is_returned, owner_name=owner_name
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def last_contact_dates(self, disc_ids):
        from app.models.pickup_event import DiscPickupNotification
        if not disc_ids:
            return {}
        result = await self.db.execute(
            select(
                DiscPickupNotification.disc_id,
                func.max(DiscPickupNotification.sent_at),
            )
            .where(DiscPickupNotification.disc_id.in_(disc_ids))
            .group_by(DiscPickupNotification.disc_id)
        )
        return {disc_id: sent_at for disc_id, sent_at in result.all()}

    async def list_by_owner_ids(self, owner_ids: list[uuid.UUID]) -> list[Disc]:
        if not owner_ids:
            return []
        result = await self.db.execute(
            select(Disc)
            .where(Disc.owner_id.in_(owner_ids), Disc.is_found == True)  # noqa: E712
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
            .order_by(Disc.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_found_by_owner_ids(self, owner_ids: list[uuid.UUID]) -> list[Disc]:
        return await self.list_by_owner_ids(owner_ids)

    async def list_wishlist_by_owner_ids(self, owner_ids: list[uuid.UUID]) -> list[Disc]:
        if not owner_ids:
            return []
        result = await self.db.execute(
            select(Disc)
            .where(Disc.owner_id.in_(owner_ids), Disc.is_found == False)  # noqa: E712
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
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
        stmt = self._apply_filters(
            stmt, is_found=is_found, is_returned=is_returned, owner_name=owner_name
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def count_by_owner_ids(self, owner_ids: list[uuid.UUID]) -> int:
        if not owner_ids:
            return 0
        result = await self.db.execute(
            select(func.count()).select_from(Disc).where(
                Disc.owner_id.in_(owner_ids),
                Disc.is_found == True,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def list_unreturned_found(self) -> list[Disc]:
        result = await self.db.execute(
            select(Disc)
            .where(
                Disc.is_found == True,  # noqa: E712
                Disc.is_returned == False,  # noqa: E712
                Disc.owner_id.isnot(None),
            )
            .options(selectinload(Disc.photos), selectinload(Disc.owner))
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
        result = await self.db.execute(select(DiscPhoto).where(DiscPhoto.id == photo_id))
        photo = result.scalar_one_or_none()
        if photo:
            path = photo.photo_path
            await self.db.delete(photo)
            await self.db.flush()
            return path
        return None
