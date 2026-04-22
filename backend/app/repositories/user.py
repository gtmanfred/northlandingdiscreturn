# backend/app/repositories/user.py
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, PhoneNumber


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, name: str, email: str, google_id: str) -> User:
        user = User(name=name, email=email, google_id=google_id)
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def get_by_id(self, user_id: uuid.UUID | str) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_google_id(self, google_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.google_id == google_id))
        return result.scalar_one_or_none()

    async def get_by_refresh_token(self, refresh_token: str) -> User | None:
        result = await self.db.execute(select(User).where(User.refresh_token == refresh_token))
        return result.scalar_one_or_none()

    async def get_by_emails(self, emails: list[str]) -> list[User]:
        if not emails:
            return []
        result = await self.db.execute(select(User).where(User.email.in_(emails)))
        return list(result.scalars().all())

    async def update(self, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            setattr(user, key, value)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def add_phone_number(self, user_id: uuid.UUID, number: str) -> PhoneNumber:
        phone = PhoneNumber(user_id=user_id, number=number)
        self.db.add(phone)
        await self.db.flush()
        await self.db.refresh(phone)
        return phone

    async def set_verification_code(
        self, phone_id: uuid.UUID, code: str, ttl_minutes: int = 10
    ) -> PhoneNumber:
        result = await self.db.execute(select(PhoneNumber).where(PhoneNumber.id == phone_id))
        phone = result.scalar_one()
        phone.verification_code = code
        phone.verification_expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        await self.db.flush()
        return phone

    async def verify_phone(self, phone_id: uuid.UUID) -> PhoneNumber:
        result = await self.db.execute(select(PhoneNumber).where(PhoneNumber.id == phone_id))
        phone = result.scalar_one()
        phone.verified = True
        phone.verification_code = None
        phone.verification_expires_at = None
        phone.verified_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(phone)
        return phone

    async def get_phone_by_number(self, user_id: uuid.UUID, number: str) -> PhoneNumber | None:
        result = await self.db.execute(
            select(PhoneNumber).where(
                PhoneNumber.user_id == user_id, PhoneNumber.number == number
            )
        )
        return result.scalar_one_or_none()

    async def get_verified_numbers(self, user_id: uuid.UUID) -> list[PhoneNumber]:
        result = await self.db.execute(
            select(PhoneNumber).where(
                PhoneNumber.user_id == user_id, PhoneNumber.verified == True  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def delete_phone(self, phone_id: uuid.UUID) -> None:
        result = await self.db.execute(select(PhoneNumber).where(PhoneNumber.id == phone_id))
        phone = result.scalar_one()
        await self.db.delete(phone)
        await self.db.flush()

    async def list_all(self) -> list[User]:
        result = await self.db.execute(
            select(User).options(selectinload(User.phone_numbers)).order_by(User.created_at)
        )
        return list(result.scalars().all())
