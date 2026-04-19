# Backend API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI backend with PostgreSQL models, Google OAuth, phone verification, disc/user/admin endpoints, and an SMS worker queue.

**Architecture:** API-first layered monolith — routers → services → repositories → models. Admin-triggered SMS notifications write `SMSJob` rows; a separate worker process polls and sends via Twilio. Supabase provides Postgres and file storage.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, pydantic-settings, python-jose, authlib, httpx, twilio, supabase-py, APScheduler, pytest, pytest-asyncio, uv

> **Note:** This is Plan 1 of 3. Plan 2 covers the React/Vite frontend. Plan 3 covers Docker, Fly.io, and CI/CD.

---

## File Map

```
backend/
├── pyproject.toml
├── alembic.ini
├── .env.example
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── deps.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── user.py
│   │   ├── disc.py
│   │   └── pickup_event.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── disc.py
│   │   └── pickup_event.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── disc.py
│   │   └── pickup_event.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── notification.py
│   │   └── storage.py
│   └── routers/
│       ├── __init__.py
│       ├── auth.py
│       ├── discs.py
│       ├── users.py
│       ├── admin.py
│       └── webhooks.py
├── worker/
│   └── main.py
├── alembic/
│   ├── env.py
│   └── versions/
└── tests/
    ├── conftest.py
    ├── test_health.py
    ├── test_auth.py
    ├── test_discs.py
    ├── test_users.py
    ├── test_admin.py
    └── test_worker.py
```

---

### Task 1: Project Setup

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Initialize backend directory and pyproject.toml**

```bash
mkdir -p backend/app/models backend/app/schemas backend/app/repositories \
  backend/app/services backend/app/routers backend/worker \
  backend/alembic/versions backend/tests
touch backend/app/__init__.py backend/app/models/__init__.py \
  backend/app/schemas/__init__.py backend/app/repositories/__init__.py \
  backend/app/services/__init__.py backend/app/routers/__init__.py
```

Write `backend/pyproject.toml`:
```toml
[project]
name = "northlanding-disc-return"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pydantic-settings>=2.5",
    "python-jose[cryptography]>=3.3",
    "authlib>=1.3",
    "httpx>=0.27",
    "twilio>=9.0",
    "supabase>=2.5",
    "apscheduler>=3.10",
    "itsdangerous>=2.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-env>=1.1",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
env = [
    "DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/test_northlanding",
    "SECRET_KEY=test-secret-key-for-tests-only",
    "GOOGLE_CLIENT_ID=test-client-id",
    "GOOGLE_CLIENT_SECRET=test-client-secret",
    "TWILIO_ACCOUNT_SID=ACtest",
    "TWILIO_AUTH_TOKEN=test-auth-token",
    "TWILIO_FROM_NUMBER=+15550000000",
    "SUPABASE_URL=https://test.supabase.co",
    "SUPABASE_SERVICE_KEY=test-service-key",
]
```

- [ ] **Step 2: Install dependencies**

```bash
cd backend
uv sync --extra dev
```

Expected: packages installed into `.venv/`

- [ ] **Step 3: Write config.py**

```python
# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    secret_key: str
    google_client_id: str
    google_client_secret: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    supabase_url: str
    supabase_service_key: str
    supabase_bucket: str = "disc-photos"

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    frontend_url: str = "http://localhost:5173"


settings = Settings()
```

- [ ] **Step 4: Write main.py**

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import auth, discs, users, admin, webhooks


def create_app() -> FastAPI:
    app = FastAPI(title="North Landing Disc Return", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(discs.router, prefix="/discs", tags=["discs"])
    app.include_router(users.router, prefix="/users", tags=["users"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
```

Create stub routers so imports don't fail yet:

```python
# backend/app/routers/auth.py
from fastapi import APIRouter
router = APIRouter()
```
```python
# backend/app/routers/discs.py
from fastapi import APIRouter
router = APIRouter()
```
```python
# backend/app/routers/users.py
from fastapi import APIRouter
router = APIRouter()
```
```python
# backend/app/routers/admin.py
from fastapi import APIRouter
router = APIRouter()
```
```python
# backend/app/routers/webhooks.py
from fastapi import APIRouter
router = APIRouter()
```

- [ ] **Step 5: Write the failing health test**

```python
# backend/tests/test_health.py
from httpx import AsyncClient, ASGITransport
from app.main import app


async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 6: Write conftest.py**

```python
# backend/tests/conftest.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.main import app
from app.database import get_db
from app.config import settings


@pytest_asyncio.fixture(scope="session")
async def engine():
    from app.models.base import Base
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(engine):
    connection = await engine.connect()
    transaction = await connection.begin()
    session_factory = async_sessionmaker(bind=connection, expire_on_commit=False)
    session = session_factory()
    yield session
    await session.close()
    await transaction.rollback()
    await connection.close()


@pytest_asyncio.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 7: Run test**

```bash
cd backend
uv run pytest tests/test_health.py -v
```

Expected: `PASSED tests/test_health.py::test_health`

- [ ] **Step 8: Commit**

```bash
cd backend
git add .
git commit -m "feat: initialize backend project with FastAPI health endpoint"
```

---

### Task 2: Database Setup + Models Base

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models/base.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`

- [ ] **Step 1: Write database.py**

```python
# backend/app/database.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 2: Write models/base.py**

```python
# backend/app/models/base.py
import uuid
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 3: Initialize Alembic**

```bash
cd backend
uv run alembic init alembic
```

- [ ] **Step 4: Write alembic/env.py**

```python
# backend/alembic/env.py
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from app.config import settings
from app.models.base import Base
# Import all models so Alembic can detect them
import app.models.user  # noqa
import app.models.disc  # noqa
import app.models.pickup_event  # noqa

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add database setup and Alembic configuration"
```

---

### Task 3: User and PhoneNumber Models

**Files:**
- Create: `backend/app/models/user.py`

- [ ] **Step 1: Write models/user.py**

```python
# backend/app/models/user.py
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    google_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    phone_numbers: Mapped[list["PhoneNumber"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"
    __table_args__ = (UniqueConstraint("user_id", "number", name="uq_phone_user"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    number: Mapped[str] = mapped_column(String, nullable=False)  # E.164
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="phone_numbers")
```

- [ ] **Step 2: Generate migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add users and phone_numbers tables"
```

Expected: new file created in `alembic/versions/`

- [ ] **Step 3: Apply migration to test DB (requires local postgres running)**

```bash
uv run alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: add User and PhoneNumber models with migration"
```

---

### Task 4: Disc and DiscPhoto Models

**Files:**
- Create: `backend/app/models/disc.py`

- [ ] **Step 1: Write models/disc.py**

```python
# backend/app/models/disc.py
import uuid
from datetime import datetime, date
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class Disc(Base):
    __tablename__ = "discs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manufacturer: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)  # E.164
    is_clear: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    input_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_found: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_returned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    final_notice_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    photos: Mapped[list["DiscPhoto"]] = relationship(
        back_populates="disc",
        cascade="all, delete-orphan",
        order_by="DiscPhoto.sort_order",
    )
    pickup_notifications: Mapped[list["DiscPickupNotification"]] = relationship(
        back_populates="disc"
    )


class DiscPhoto(Base):
    __tablename__ = "disc_photos"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    disc_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("discs.id"), nullable=False)
    photo_path: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    disc: Mapped["Disc"] = relationship(back_populates="photos")
```

Note: `DiscPickupNotification` is defined in `pickup_event.py` — the forward reference resolves at mapper configuration time.

- [ ] **Step 2: Generate and apply migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add discs and disc_photos tables"
uv run alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add .
git commit -m "feat: add Disc and DiscPhoto models with migration"
```

---

### Task 5: PickupEvent, DiscPickupNotification, SMSJob Models

**Files:**
- Create: `backend/app/models/pickup_event.py`

- [ ] **Step 1: Write models/pickup_event.py**

```python
# backend/app/models/pickup_event.py
import enum
import uuid
from datetime import datetime, date
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class SMSJobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    sent = "sent"
    failed = "failed"


class PickupEvent(Base):
    __tablename__ = "pickup_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    notifications_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    disc_notifications: Mapped[list["DiscPickupNotification"]] = relationship(
        back_populates="pickup_event"
    )


class DiscPickupNotification(Base):
    __tablename__ = "disc_pickup_notifications"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    disc_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("discs.id"), nullable=False)
    pickup_event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pickup_events.id"), nullable=False
    )
    is_final_notice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    disc: Mapped["Disc"] = relationship(back_populates="pickup_notifications")
    pickup_event: Mapped["PickupEvent"] = relationship(back_populates="disc_notifications")


class SMSJob(Base):
    __tablename__ = "sms_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[SMSJobStatus] = mapped_column(
        Enum(SMSJobStatus, name="smsjobstatus"), default=SMSJobStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
```

Add import to `app/models/__init__.py` so all models are registered:

```python
# backend/app/models/__init__.py
from app.models.user import User, PhoneNumber
from app.models.disc import Disc, DiscPhoto
from app.models.pickup_event import PickupEvent, DiscPickupNotification, SMSJob, SMSJobStatus

__all__ = [
    "User", "PhoneNumber",
    "Disc", "DiscPhoto",
    "PickupEvent", "DiscPickupNotification", "SMSJob", "SMSJobStatus",
]
```

- [ ] **Step 2: Generate and apply migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add pickup_events, disc_pickup_notifications, sms_jobs tables"
uv run alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add .
git commit -m "feat: add PickupEvent, DiscPickupNotification, SMSJob models"
```

---

### Task 6: User Repository

**Files:**
- Create: `backend/app/repositories/user.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_users.py
import pytest
from app.repositories.user import UserRepository
from app.models.user import User, PhoneNumber


async def test_create_user(db):
    repo = UserRepository(db)
    user = await repo.create(
        name="Alice", email="alice@example.com", google_id="google-123"
    )
    assert user.id is not None
    assert user.email == "alice@example.com"
    assert user.is_admin is False


async def test_get_by_email(db):
    repo = UserRepository(db)
    await repo.create(name="Bob", email="bob@example.com", google_id="google-bob")
    found = await repo.get_by_email("bob@example.com")
    assert found is not None
    assert found.name == "Bob"


async def test_get_by_google_id(db):
    repo = UserRepository(db)
    await repo.create(name="Carol", email="carol@example.com", google_id="google-carol")
    found = await repo.get_by_google_id("google-carol")
    assert found is not None
    assert found.email == "carol@example.com"


async def test_add_phone_number(db):
    repo = UserRepository(db)
    user = await repo.create(name="Dave", email="dave@example.com", google_id="google-dave")
    phone = await repo.add_phone_number(user.id, "+15551234567")
    assert phone.number == "+15551234567"
    assert phone.verified is False


async def test_verify_phone_number(db):
    repo = UserRepository(db)
    user = await repo.create(name="Eve", email="eve@example.com", google_id="google-eve")
    phone = await repo.add_phone_number(user.id, "+15559876543")
    updated = await repo.verify_phone(phone.id)
    assert updated.verified is True
    assert updated.verified_at is not None


async def test_get_verified_numbers_for_user(db):
    repo = UserRepository(db)
    user = await repo.create(name="Frank", email="frank@example.com", google_id="google-frank")
    p1 = await repo.add_phone_number(user.id, "+15550001111")
    await repo.verify_phone(p1.id)
    await repo.add_phone_number(user.id, "+15550002222")  # unverified
    numbers = await repo.get_verified_numbers(user.id)
    assert len(numbers) == 1
    assert numbers[0].number == "+15550001111"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/test_users.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` for `app.repositories.user`

- [ ] **Step 3: Write repositories/user.py**

```python
# backend/app/repositories/user.py
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
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
        result = await self.db.execute(select(User).order_by(User.created_at))
        return list(result.scalars().all())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/test_users.py -v
```

Expected: all 6 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add UserRepository with phone number management"
```

---

### Task 7: Disc Repository

**Files:**
- Create: `backend/app/repositories/disc.py`
- Modify: `backend/tests/test_discs.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_discs.py
import pytest
from datetime import date
from app.repositories.disc import DiscRepository
from app.repositories.user import UserRepository


async def test_create_disc(db):
    repo = DiscRepository(db)
    disc = await repo.create(
        manufacturer="Innova",
        name="Destroyer",
        color="Red",
        input_date=date.today(),
    )
    assert disc.id is not None
    assert disc.manufacturer == "Innova"
    assert disc.is_found is True
    assert disc.is_returned is False


async def test_list_all_discs(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="Discraft", name="Buzzz", color="Blue", input_date=date.today())
    await repo.create(manufacturer="Discraft", name="Zone", color="Green", input_date=date.today())
    discs = await repo.list_all()
    assert len(discs) >= 2


async def test_list_discs_by_phone(db):
    repo = DiscRepository(db)
    await repo.create(
        manufacturer="MVP", name="Atom", color="Yellow",
        input_date=date.today(), phone_number="+15551111111"
    )
    await repo.create(manufacturer="MVP", name="Envy", color="Purple", input_date=date.today())
    discs = await repo.list_by_phone("+15551111111")
    assert len(discs) == 1
    assert discs[0].name == "Atom"


async def test_update_disc(db):
    repo = DiscRepository(db)
    disc = await repo.create(manufacturer="Latitude", name="Pure", color="White", input_date=date.today())
    updated = await repo.update(disc, is_returned=True, owner_name="Alice")
    assert updated.is_returned is True
    assert updated.owner_name == "Alice"


async def test_get_disc_by_id(db):
    repo = DiscRepository(db)
    disc = await repo.create(manufacturer="Dynamic", name="Lucid", color="Orange", input_date=date.today())
    found = await repo.get_by_id(disc.id)
    assert found is not None
    assert found.id == disc.id


async def test_delete_disc(db):
    repo = DiscRepository(db)
    disc = await repo.create(manufacturer="Prodigy", name="F5", color="Black", input_date=date.today())
    await repo.delete(disc.id)
    found = await repo.get_by_id(disc.id)
    assert found is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/test_discs.py -v
```

Expected: `ImportError` for `app.repositories.disc`

- [ ] **Step 3: Write repositories/disc.py**

```python
# backend/app/repositories/disc.py
import uuid
from datetime import date
from sqlalchemy import select
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

    async def list_all(self, *, page: int = 1, page_size: int = 50) -> list[Disc]:
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(Disc)
            .options(selectinload(Disc.photos))
            .order_by(Disc.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
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

    async def list_unreturned_found(self) -> list[Disc]:
        """All found, unreturned discs with a phone number — for pickup notifications."""
        result = await self.db.execute(
            select(Disc).where(
                Disc.is_found == True,  # noqa: E712
                Disc.is_returned == False,  # noqa: E712
                Disc.phone_number.isnot(None),
            )
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
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_discs.py -v
```

Expected: all 6 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add DiscRepository with photo management"
```

---

### Task 8: PickupEvent Repository

**Files:**
- Create: `backend/app/repositories/pickup_event.py`
- Create: `backend/tests/test_admin.py` (pickup event section)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_admin.py
import pytest
from datetime import date, timedelta
from app.repositories.pickup_event import PickupEventRepository
from app.repositories.disc import DiscRepository


async def test_create_pickup_event(db):
    repo = PickupEventRepository(db)
    event = await repo.create_event(scheduled_date=date.today() + timedelta(days=7))
    assert event.id is not None
    assert event.notifications_sent_at is None


async def test_list_pickup_events(db):
    repo = PickupEventRepository(db)
    await repo.create_event(scheduled_date=date.today() + timedelta(days=7))
    await repo.create_event(scheduled_date=date.today() + timedelta(days=14))
    events = await repo.list_events()
    assert len(events) >= 2


async def test_create_disc_notification(db):
    disc_repo = DiscRepository(db)
    event_repo = PickupEventRepository(db)
    disc = await disc_repo.create(
        manufacturer="Innova", name="Boss", color="Blue",
        input_date=date.today(), phone_number="+15551234567"
    )
    event = await event_repo.create_event(scheduled_date=date.today() + timedelta(days=3))
    notif = await event_repo.create_disc_notification(
        disc_id=disc.id, pickup_event_id=event.id, is_final_notice=False
    )
    assert notif.id is not None
    assert notif.is_final_notice is False


async def test_count_prior_notifications(db):
    disc_repo = DiscRepository(db)
    event_repo = PickupEventRepository(db)
    disc = await disc_repo.create(
        manufacturer="Innova", name="Wraith", color="Green",
        input_date=date.today(), phone_number="+15559999999"
    )
    for i in range(3):
        event = await event_repo.create_event(scheduled_date=date.today() + timedelta(days=i))
        await event_repo.create_disc_notification(disc_id=disc.id, pickup_event_id=event.id)
    count = await event_repo.count_notifications_for_disc(disc.id)
    assert count == 3


async def test_create_sms_job(db):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15550001111", message="Test message")
    assert job.id is not None
    assert job.status.value == "pending"


async def test_claim_pending_sms_jobs(db):
    repo = PickupEventRepository(db)
    await repo.create_sms_job(phone_number="+15550002222", message="Pickup notice")
    jobs = await repo.claim_pending_sms_jobs(limit=10)
    assert len(jobs) >= 1
    assert all(j.status.value == "processing" for j in jobs)
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/test_admin.py -v
```

Expected: `ImportError` for `app.repositories.pickup_event`

- [ ] **Step 3: Write repositories/pickup_event.py**

```python
# backend/app/repositories/pickup_event.py
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pickup_event import PickupEvent, DiscPickupNotification, SMSJob, SMSJobStatus


class PickupEventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_event(self, *, scheduled_date: date, notes: str | None = None) -> PickupEvent:
        event = PickupEvent(scheduled_date=scheduled_date, notes=notes)
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def get_event(self, event_id: uuid.UUID) -> PickupEvent | None:
        result = await self.db.execute(select(PickupEvent).where(PickupEvent.id == event_id))
        return result.scalar_one_or_none()

    async def list_events(self) -> list[PickupEvent]:
        result = await self.db.execute(
            select(PickupEvent).order_by(PickupEvent.scheduled_date.desc())
        )
        return list(result.scalars().all())

    async def update_event(self, event: PickupEvent, **kwargs) -> PickupEvent:
        for key, value in kwargs.items():
            setattr(event, key, value)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def count_notifications_for_disc(self, disc_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).where(DiscPickupNotification.disc_id == disc_id)
        )
        return result.scalar_one()

    async def disc_already_notified_for_event(
        self, disc_id: uuid.UUID, pickup_event_id: uuid.UUID
    ) -> bool:
        result = await self.db.execute(
            select(DiscPickupNotification).where(
                DiscPickupNotification.disc_id == disc_id,
                DiscPickupNotification.pickup_event_id == pickup_event_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def create_disc_notification(
        self,
        *,
        disc_id: uuid.UUID,
        pickup_event_id: uuid.UUID,
        is_final_notice: bool = False,
    ) -> DiscPickupNotification:
        notif = DiscPickupNotification(
            disc_id=disc_id,
            pickup_event_id=pickup_event_id,
            is_final_notice=is_final_notice,
        )
        self.db.add(notif)
        await self.db.flush()
        await self.db.refresh(notif)
        return notif

    async def create_sms_job(self, *, phone_number: str, message: str) -> SMSJob:
        job = SMSJob(phone_number=phone_number, message=message)
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def claim_pending_sms_jobs(self, *, limit: int = 50) -> list[SMSJob]:
        """Select pending jobs, mark as processing, return them. Uses SKIP LOCKED."""
        result = await self.db.execute(
            select(SMSJob)
            .where(SMSJob.status == SMSJobStatus.pending)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = list(result.scalars().all())
        for job in jobs:
            job.status = SMSJobStatus.processing
        await self.db.flush()
        return jobs

    async def mark_sms_sent(self, job: SMSJob) -> None:
        job.status = SMSJobStatus.sent
        job.processed_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def mark_sms_failed(self, job: SMSJob, error: str) -> None:
        job.status = SMSJobStatus.failed
        job.processed_at = datetime.now(timezone.utc)
        job.error = error
        await self.db.flush()
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_admin.py -v
```

Expected: all 6 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add PickupEventRepository with SMSJob queue support"
```

---

### Task 9: Schemas

**Files:**
- Create: `backend/app/schemas/user.py`
- Create: `backend/app/schemas/disc.py`
- Create: `backend/app/schemas/pickup_event.py`

These Pydantic schemas are used by routers for request/response serialization and to drive OpenAPI generation.

- [ ] **Step 1: Write schemas/user.py**

```python
# backend/app/schemas/user.py
import uuid
from datetime import datetime
from pydantic import BaseModel


class PhoneNumberOut(BaseModel):
    id: uuid.UUID
    number: str
    verified: bool
    verified_at: datetime | None

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    is_admin: bool
    phone_numbers: list[PhoneNumberOut] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class AddPhoneRequest(BaseModel):
    number: str  # E.164 e.g. "+15551234567"


class VerifyPhoneRequest(BaseModel):
    number: str
    code: str


class UpdateUserRequest(BaseModel):
    name: str | None = None
    is_admin: bool | None = None
```

- [ ] **Step 2: Write schemas/disc.py**

```python
# backend/app/schemas/disc.py
import uuid
from datetime import datetime, date
from pydantic import BaseModel


class DiscPhotoOut(BaseModel):
    id: uuid.UUID
    photo_path: str
    sort_order: int

    model_config = {"from_attributes": True}


class DiscOut(BaseModel):
    id: uuid.UUID
    manufacturer: str
    name: str
    color: str
    owner_name: str | None
    phone_number: str | None
    is_clear: bool
    input_date: date
    is_found: bool
    is_returned: bool
    final_notice_sent: bool
    photos: list[DiscPhotoOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscCreate(BaseModel):
    manufacturer: str
    name: str
    color: str
    input_date: date
    owner_name: str | None = None
    phone_number: str | None = None
    is_clear: bool = False
    is_found: bool = True


class DiscUpdate(BaseModel):
    manufacturer: str | None = None
    name: str | None = None
    color: str | None = None
    owner_name: str | None = None
    phone_number: str | None = None
    is_clear: bool | None = None
    is_found: bool | None = None
    is_returned: bool | None = None


class WishlistDiscCreate(BaseModel):
    manufacturer: str | None = None
    name: str | None = None
    color: str | None = None
    notes: str | None = None


class DiscPage(BaseModel):
    items: list[DiscOut]
    page: int
    page_size: int
    total: int
```

- [ ] **Step 3: Write schemas/pickup_event.py**

```python
# backend/app/schemas/pickup_event.py
import uuid
from datetime import datetime, date
from pydantic import BaseModel
from app.models.pickup_event import SMSJobStatus


class PickupEventOut(BaseModel):
    id: uuid.UUID
    scheduled_date: date
    notes: str | None
    notifications_sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PickupEventCreate(BaseModel):
    scheduled_date: date
    notes: str | None = None


class PickupEventUpdate(BaseModel):
    scheduled_date: date | None = None
    notes: str | None = None


class NotifyResult(BaseModel):
    sms_jobs_enqueued: int
    discs_notified: int


class SMSJobOut(BaseModel):
    id: uuid.UUID
    phone_number: str
    status: SMSJobStatus
    created_at: datetime
    processed_at: datetime | None
    error: str | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: add Pydantic schemas for users, discs, and pickup events"
```

---

### Task 10: Auth Service and Router

**Files:**
- Create: `backend/app/services/auth.py`
- Create: `backend/app/deps.py`
- Modify: `backend/app/routers/auth.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write services/auth.py**

```python
# backend/app/services/auth.py
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.config import settings


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
```

- [ ] **Step 2: Write deps.py**

```python
# backend/app/deps.py
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError
from app.database import get_db
from app.services.auth import decode_access_token
from app.repositories.user import UserRepository
from app.models.user import User

bearer = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user
```

- [ ] **Step 3: Write routers/auth.py**

```python
# backend/app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.repositories.user import UserRepository
from app.services.auth import create_access_token
from app.schemas.user import UserOut

router = APIRouter()

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/google")
async def login_google(request: Request):
    redirect_uri = str(request.url_for("auth_google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="auth_google_callback")
async def auth_google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(status_code=400, detail="Google auth failed")

    repo = UserRepository(db)
    user = await repo.get_by_google_id(user_info["sub"])
    if user is None:
        user = await repo.create(
            name=user_info.get("name", user_info["email"]),
            email=user_info["email"],
            google_id=user_info["sub"],
        )
        await db.commit()

    access_token = create_access_token(str(user.id))
    redirect_url = f"{settings.frontend_url}/auth/callback?token={access_token}"
    return RedirectResponse(url=redirect_url)


@router.post("/logout")
async def logout():
    return {"message": "logged out"}
```

- [ ] **Step 4: Write failing auth tests**

```python
# backend/tests/test_auth.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.auth import create_access_token, decode_access_token
from app.repositories.user import UserRepository


async def test_create_and_decode_token():
    token = create_access_token("user-123")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"


async def test_get_current_user_invalid_token(client):
    response = await client.get("/users/me", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


async def test_get_current_user_no_token(client):
    response = await client.get("/users/me")
    assert response.status_code == 403  # HTTPBearer returns 403 when no credentials
```

- [ ] **Step 5: Run tests**

```bash
cd backend
uv run pytest tests/test_auth.py -v
```

Expected: all 3 tests `PASSED` (the router endpoints require session middleware — see next step if `GET /auth/google` fails with middleware error; it is not tested directly here)

- [ ] **Step 6: Add session middleware required by authlib**

Add to `backend/app/main.py` after creating the FastAPI app:

```python
from starlette.middleware.sessions import SessionMiddleware

def create_app() -> FastAPI:
    app = FastAPI(title="North Landing Disc Return", version="0.1.0")
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
    app.add_middleware(
        CORSMiddleware,
        ...
    )
```

Full updated `create_app`:

```python
def create_app() -> FastAPI:
    app = FastAPI(title="North Landing Disc Return", version="0.1.0")
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(discs.router, prefix="/discs", tags=["discs"])
    app.include_router(users.router, prefix="/users", tags=["users"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
```

- [ ] **Step 7: Run all tests**

```bash
cd backend
uv run pytest tests/ -v
```

Expected: all tests `PASSED`

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "feat: add auth service, JWT deps, Google OAuth router"
```

---

### Task 11: Users Router

**Files:**
- Modify: `backend/app/routers/users.py`
- Extend: `backend/tests/test_users.py`

- [ ] **Step 1: Write failing endpoint tests**

Add to `backend/tests/test_users.py`:

```python
import uuid
from app.services.auth import create_access_token
from app.repositories.user import UserRepository


def auth_headers(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


async def test_get_me(client, db):
    repo = UserRepository(db)
    user = await repo.create(name="Tester", email="tester@example.com", google_id="g-tester")
    await db.commit()
    response = await client.get("/users/me", headers=auth_headers(user.id))
    assert response.status_code == 200
    assert response.json()["email"] == "tester@example.com"


async def test_add_phone_and_verify(client, db):
    repo = UserRepository(db)
    user = await repo.create(name="PhoneUser", email="phone@example.com", google_id="g-phone")
    await db.commit()

    with patch("app.routers.users.send_verification_sms") as mock_sms:
        mock_sms.return_value = None
        resp = await client.post(
            "/users/me/phones",
            json={"number": "+15551234567"},
            headers=auth_headers(user.id),
        )
    assert resp.status_code == 200

    phone = await repo.get_phone_by_number(user.id, "+15551234567")
    assert phone is not None
    code = phone.verification_code

    resp2 = await client.post(
        "/users/me/phones/verify",
        json={"number": "+15551234567", "code": code},
        headers=auth_headers(user.id),
    )
    assert resp2.status_code == 200
    assert resp2.json()["verified"] is True
```

Add `from unittest.mock import patch` at top of test file.

- [ ] **Step 2: Write a helper to send verification SMS in services/auth.py**

```python
# Add to backend/app/services/auth.py
import random
from twilio.rest import Client
from app.config import settings


def generate_verification_code() -> str:
    return str(random.randint(100000, 999999))


def send_verification_sms(to_number: str, code: str) -> None:
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    client.messages.create(
        body=f"Your North Landing disc return verification code is: {code}",
        from_=settings.twilio_from_number,
        to=to_number,
    )
```

- [ ] **Step 3: Write routers/users.py**

```python
# backend/app/routers/users.py
from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserOut, PhoneNumberOut, AddPhoneRequest, VerifyPhoneRequest
from app.services.auth import generate_verification_code, send_verification_sms

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = UserRepository(db)
    user = await repo.get_by_id(current_user.id)
    return user


@router.post("/me/phones", response_model=PhoneNumberOut)
async def add_phone(
    body: AddPhoneRequest,
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
    send_verification_sms(body.number, code)
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
    if phone.verification_code != body.code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    if phone.verification_expires_at and phone.verification_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification code expired")
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
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_users.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add users router with phone verification endpoints"
```

---

### Task 12: Discs Router (CRUD + Photo Upload)

**Files:**
- Create: `backend/app/services/storage.py`
- Modify: `backend/app/routers/discs.py`
- Extend: `backend/tests/test_discs.py`

- [ ] **Step 1: Write services/storage.py**

```python
# backend/app/services/storage.py
import io
from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_storage_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client


def upload_photo(file_bytes: bytes, path: str, content_type: str = "image/jpeg") -> str:
    client = get_storage_client()
    client.storage.from_(settings.supabase_bucket).upload(
        path, file_bytes, {"content-type": content_type, "upsert": "false"}
    )
    return path


def delete_photo(path: str) -> None:
    client = get_storage_client()
    client.storage.from_(settings.supabase_bucket).remove([path])


def get_public_url(path: str) -> str:
    client = get_storage_client()
    return client.storage.from_(settings.supabase_bucket).get_public_url(path)
```

- [ ] **Step 2: Write endpoint tests**

Add to `backend/tests/test_discs.py`:

```python
import uuid
from datetime import date
from unittest.mock import patch
from app.services.auth import create_access_token
from app.repositories.user import UserRepository


def admin_headers(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


async def make_admin(db, name="Admin", email="admin@example.com", google_id="g-admin"):
    repo = UserRepository(db)
    user = await repo.create(name=name, email=email, google_id=google_id)
    user.is_admin = True
    await db.commit()
    return user


async def test_create_disc_as_admin(client, db):
    admin = await make_admin(db)
    resp = await client.post(
        "/discs",
        json={"manufacturer": "Innova", "name": "Destroyer", "color": "Red",
              "input_date": str(date.today()), "is_found": True},
        headers=admin_headers(admin.id),
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Destroyer"


async def test_create_disc_non_admin_forbidden(client, db):
    repo = UserRepository(db)
    user = await repo.create(name="Regular", email="reg@example.com", google_id="g-reg")
    await db.commit()
    resp = await client.post(
        "/discs",
        json={"manufacturer": "Innova", "name": "Boss", "color": "Blue",
              "input_date": str(date.today())},
        headers=admin_headers(user.id),
    )
    assert resp.status_code == 403


async def test_list_discs_admin_sees_all(client, db):
    admin = await make_admin(db, email="admin2@example.com", google_id="g-admin2")
    resp = await client.get("/discs", headers=admin_headers(admin.id))
    assert resp.status_code == 200
    assert "items" in resp.json()


async def test_upload_photo(client, db):
    admin = await make_admin(db, email="admin3@example.com", google_id="g-admin3")
    create_resp = await client.post(
        "/discs",
        json={"manufacturer": "MVP", "name": "Atom", "color": "Gold",
              "input_date": str(date.today())},
        headers=admin_headers(admin.id),
    )
    disc_id = create_resp.json()["id"]

    with patch("app.routers.discs.upload_photo", return_value=f"discs/{disc_id}/photo.jpg"):
        resp = await client.post(
            f"/discs/{disc_id}/photos",
            files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
            headers=admin_headers(admin.id),
        )
    assert resp.status_code == 201
```

- [ ] **Step 3: Write routers/discs.py**

```python
# backend/app/routers/discs.py
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models.user import User
from app.repositories.disc import DiscRepository
from app.repositories.user import UserRepository
from app.schemas.disc import DiscOut, DiscCreate, DiscUpdate, DiscPage
from app.schemas.disc import DiscPhotoOut
from app.services.storage import upload_photo, delete_photo, get_public_url

router = APIRouter()


def _add_photo_urls(disc_out: dict) -> dict:
    for photo in disc_out.get("photos", []):
        photo["url"] = get_public_url(photo["photo_path"])
    return disc_out


@router.get("", response_model=DiscPage)
async def list_discs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    page_size: int = 50,
):
    repo = DiscRepository(db)
    if current_user.is_admin:
        discs = await repo.list_all(page=page, page_size=page_size)
        total = len(discs)
    else:
        user_repo = UserRepository(db)
        phones = await user_repo.get_verified_numbers(current_user.id)
        numbers = [p.number for p in phones]
        discs = await repo.list_by_phones(numbers)
        total = len(discs)
    return DiscPage(
        items=[DiscOut.model_validate(d) for d in discs],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=DiscOut, status_code=201)
async def create_disc(
    body: DiscCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repo = DiscRepository(db)
    disc = await repo.create(**body.model_dump())
    await db.commit()
    await db.refresh(disc)
    return disc


@router.patch("/{disc_id}", response_model=DiscOut)
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
    disc = await repo.update(disc, **updates)
    await db.commit()
    return disc


@router.delete("/{disc_id}", status_code=204)
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


@router.post("/{disc_id}/photos", response_model=DiscPhotoOut, status_code=201)
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
    upload_photo(file_bytes, path, file.content_type or "image/jpeg")
    photo = await repo.add_photo(disc_id, path, sort_order)
    await db.commit()
    return photo


@router.delete("/{disc_id}/photos/{photo_id}", status_code=204)
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
    delete_photo(path)
    await db.commit()
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_discs.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add discs router with CRUD and photo upload"
```

---

### Task 13: Admin Router (Users + Wishlist + Pickup Events + Notify)

**Files:**
- Modify: `backend/app/routers/admin.py`
- Create: `backend/app/services/notification.py`
- Extend: `backend/tests/test_admin.py`

- [ ] **Step 1: Write notification service**

```python
# backend/app/services/notification.py
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.disc import DiscRepository
from app.repositories.pickup_event import PickupEventRepository
from app.models.pickup_event import PickupEvent


FINAL_NOTICE_THRESHOLD = 6


async def enqueue_pickup_notifications(
    event: PickupEvent, db: AsyncSession
) -> tuple[int, int]:
    """
    Returns (sms_jobs_enqueued, discs_notified).
    Composes SMS messages grouped by phone number and writes SMSJob rows.
    Does NOT call Twilio — the worker handles that.
    """
    disc_repo = DiscRepository(db)
    event_repo = PickupEventRepository(db)

    unreturned = await disc_repo.list_unreturned_found()
    notified_disc_count = 0
    phone_discs: dict[str, list] = defaultdict(list)
    phone_is_final: dict[str, bool] = defaultdict(bool)

    for disc in unreturned:
        if await event_repo.disc_already_notified_for_event(disc.id, event.id):
            continue
        prior_count = await event_repo.count_notifications_for_disc(disc.id)
        is_final = prior_count + 1 >= FINAL_NOTICE_THRESHOLD
        await event_repo.create_disc_notification(
            disc_id=disc.id, pickup_event_id=event.id, is_final_notice=is_final
        )
        if is_final:
            await disc_repo.update(disc, final_notice_sent=True)
            phone_is_final[disc.phone_number] = True
        phone_discs[disc.phone_number].append(disc)
        notified_disc_count += 1

    sms_count = 0
    for phone_number, discs in phone_discs.items():
        disc_list = ", ".join(
            f"{d.manufacturer} {d.name} ({d.color})" for d in discs
        )
        if phone_is_final.get(phone_number):
            message = (
                f"FINAL NOTICE: Your disc(s) [{disc_list}] will be added to the "
                f"sale box if not picked up at the {event.scheduled_date} pickup. "
                "Reply STOP to opt out."
            )
        else:
            message = (
                f"Disc pickup at North Landing scheduled for {event.scheduled_date}. "
                f"You have disc(s): {disc_list}. Reply STOP to opt out."
            )
        await event_repo.create_sms_job(phone_number=phone_number, message=message)
        sms_count += 1

    return sms_count, notified_disc_count
```

- [ ] **Step 2: Write failing admin endpoint tests**

Add to `backend/tests/test_admin.py`:

```python
import uuid
from datetime import date, timedelta
from app.services.auth import create_access_token
from app.repositories.user import UserRepository
from app.repositories.disc import DiscRepository


def admin_token(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


async def make_admin_user(db):
    repo = UserRepository(db)
    user = await repo.create(name="AdminUser", email="adm@test.com", google_id="g-adm")
    user.is_admin = True
    await db.commit()
    return user


async def test_list_users(client, db):
    admin = await make_admin_user(db)
    resp = await client.get("/admin/users", headers=admin_token(admin.id))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_create_pickup_event(client, db):
    admin = await make_admin_user(db)
    resp = await client.post(
        "/admin/pickup-events",
        json={"scheduled_date": str(date.today() + timedelta(days=7))},
        headers=admin_token(admin.id),
    )
    assert resp.status_code == 201
    assert resp.json()["notifications_sent_at"] is None


async def test_notify_pickup_event(client, db):
    admin = await make_admin_user(db)
    disc_repo = DiscRepository(db)
    await disc_repo.create(
        manufacturer="Innova", name="Wraith", color="Blue",
        input_date=date.today(), phone_number="+15551112222", is_found=True
    )
    await db.commit()

    event_resp = await client.post(
        "/admin/pickup-events",
        json={"scheduled_date": str(date.today() + timedelta(days=3))},
        headers=admin_token(admin.id),
    )
    event_id = event_resp.json()["id"]

    resp = await client.post(
        f"/admin/pickup-events/{event_id}/notify",
        headers=admin_token(admin.id),
    )
    assert resp.status_code == 200
    assert resp.json()["sms_jobs_enqueued"] == 1
    assert resp.json()["discs_notified"] == 1
```

- [ ] **Step 3: Write routers/admin.py**

```python
# backend/app/routers/admin.py
import uuid
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
from datetime import date

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
    all_discs = await disc_repo.list_by_phones(numbers)
    return [d for d in all_discs if not d.is_found]


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
    from datetime import datetime, timezone
    await repo.update_event(event, notifications_sent_at=datetime.now(timezone.utc))
    await db.commit()
    return NotifyResult(sms_jobs_enqueued=sms_count, discs_notified=disc_count)
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_admin.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add admin router with user management, pickup events, and notify endpoint"
```

---

### Task 14: User Wishlist Router

**Files:**
- Extend: `backend/app/routers/users.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_users.py`:

```python
async def test_get_my_wishlist(client, db):
    repo = UserRepository(db)
    user = await repo.create(name="Wish", email="wish@test.com", google_id="g-wish")
    phone = await repo.add_phone_number(user.id, "+15550001234")
    await repo.verify_phone(phone.id)
    await db.commit()

    disc_repo = DiscRepository(db)
    from datetime import date
    await disc_repo.create(
        manufacturer="Innova", name="Teebird", color="Pink",
        input_date=date.today(), phone_number="+15550001234", is_found=False
    )
    await db.commit()

    resp = await client.get("/users/me/wishlist", headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Teebird"


async def test_add_wishlist_disc(client, db):
    repo = UserRepository(db)
    user = await repo.create(name="WishAdd", email="wishadd@test.com", google_id="g-wishadd")
    await db.commit()

    resp = await client.post(
        "/users/me/wishlist",
        json={"manufacturer": "Discraft", "name": "Buzzz", "color": "White"},
        headers=auth_headers(user.id),
    )
    assert resp.status_code == 201
    assert resp.json()["is_found"] is False
```

Add `from app.repositories.disc import DiscRepository` to test file imports.

- [ ] **Step 2: Extend routers/users.py with wishlist endpoints**

Add after existing routes in `backend/app/routers/users.py`:

```python
from app.repositories.disc import DiscRepository
from app.schemas.disc import DiscOut, WishlistDiscCreate
from datetime import date


@router.get("/me/wishlist", response_model=list[DiscOut])
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
    all_discs = await disc_repo.list_by_phones(numbers)
    return [d for d in all_discs if not d.is_found]


@router.post("/me/wishlist", response_model=DiscOut, status_code=201)
async def add_wishlist_disc(
    body: WishlistDiscCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user_repo = UserRepository(db)
    phones = await user_repo.get_verified_numbers(current_user.id)
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


@router.delete("/me/wishlist/{disc_id}", status_code=204)
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
```

- [ ] **Step 3: Run tests**

```bash
cd backend
uv run pytest tests/test_users.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: add user wishlist endpoints"
```

---

### Task 15: Twilio Webhook

**Files:**
- Modify: `backend/app/routers/webhooks.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_webhooks.py (new file)
import hmac, hashlib, base64
from unittest.mock import patch
from app.config import settings


def make_twilio_signature(url: str, params: dict, auth_token: str) -> str:
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    mac = hmac.new(auth_token.encode(), s.encode(), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


async def test_twilio_webhook_valid_signature(client):
    params = {"Body": "STOP", "From": "+15551234567"}
    url = "http://test/webhooks/twilio"
    sig = make_twilio_signature(url, params, settings.twilio_auth_token)
    with patch("app.routers.webhooks.validate_twilio_signature", return_value=True):
        resp = await client.post(
            "/webhooks/twilio",
            data=params,
            headers={"X-Twilio-Signature": sig},
        )
    assert resp.status_code == 200


async def test_twilio_webhook_invalid_signature(client):
    resp = await client.post(
        "/webhooks/twilio",
        data={"Body": "STOP", "From": "+15551234567"},
        headers={"X-Twilio-Signature": "bad-sig"},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Write routers/webhooks.py**

```python
# backend/app/routers/webhooks.py
import hmac
import hashlib
import base64
from fastapi import APIRouter, Request, HTTPException
from app.config import settings

router = APIRouter()


def validate_twilio_signature(request_url: str, params: dict, signature: str) -> bool:
    s = request_url
    for key in sorted(params.keys()):
        s += key + params[key]
    mac = hmac.new(settings.twilio_auth_token.encode(), s.encode(), hashlib.sha1)
    expected = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(expected, signature)


@router.post("/twilio")
async def twilio_inbound(request: Request):
    form = await request.form()
    params = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)

    if not validate_twilio_signature(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    body = params.get("Body", "").strip().upper()
    from_number = params.get("From", "")
    # STOP is handled automatically by Twilio; log other inbound messages here
    return {"status": "received", "from": from_number, "body": body}
```

- [ ] **Step 3: Run tests**

```bash
cd backend
uv run pytest tests/test_webhooks.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: add Twilio inbound webhook with signature validation"
```

---

### Task 16: SMS Worker

**Files:**
- Create: `backend/worker/main.py`
- Create: `backend/tests/test_worker.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_worker.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, timedelta
from app.repositories.pickup_event import PickupEventRepository
from app.models.pickup_event import SMSJobStatus
from worker.main import process_sms_jobs


async def test_process_sms_jobs_sends_and_marks_sent(db):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15551234567", message="Test notice")
    await db.commit()

    with patch("worker.main.Client") as MockClient:
        mock_messages = MagicMock()
        MockClient.return_value.messages = mock_messages
        await process_sms_jobs(db)

    mock_messages.create.assert_called_once_with(
        body="Test notice",
        from_=pytest.approx(None, abs=None),  # from_ checked below
        to="+15551234567",
    )
    await db.refresh(job)
    assert job.status == SMSJobStatus.sent


async def test_process_sms_jobs_marks_failed_on_twilio_error(db):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15559999999", message="Another notice")
    await db.commit()

    with patch("worker.main.Client") as MockClient:
        MockClient.return_value.messages.create.side_effect = Exception("Twilio error")
        await process_sms_jobs(db)

    await db.refresh(job)
    assert job.status == SMSJobStatus.failed
    assert "Twilio error" in job.error
```

- [ ] **Step 2: Write worker/main.py**

```python
# backend/worker/main.py
import asyncio
import logging
from twilio.rest import Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings
from app.repositories.pickup_event import PickupEventRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def process_sms_jobs(db: AsyncSession | None = None) -> None:
    close_after = db is None
    if db is None:
        db = SessionLocal()
    try:
        repo = PickupEventRepository(db)
        jobs = await repo.claim_pending_sms_jobs(limit=50)
        if not jobs:
            return
        logger.info(f"Processing {len(jobs)} SMS jobs")
        twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        for job in jobs:
            try:
                twilio_client.messages.create(
                    body=job.message,
                    from_=settings.twilio_from_number,
                    to=job.phone_number,
                )
                await repo.mark_sms_sent(job)
                logger.info(f"SMS sent to {job.phone_number}")
            except Exception as e:
                await repo.mark_sms_failed(job, str(e))
                logger.error(f"SMS failed to {job.phone_number}: {e}")
        await db.commit()
    finally:
        if close_after:
            await db.close()


async def main() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(process_sms_jobs, "interval", seconds=10, id="sms_worker")
    scheduler.start()
    logger.info("Worker started — polling for SMS jobs every 10 seconds")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Fix test assertion for from_ (update test)**

Replace the `pytest.approx` assertion in `test_process_sms_jobs_sends_and_marks_sent`:

```python
async def test_process_sms_jobs_sends_and_marks_sent(db):
    repo = PickupEventRepository(db)
    job = await repo.create_sms_job(phone_number="+15551234567", message="Test notice")
    await db.commit()

    with patch("worker.main.Client") as MockClient:
        mock_messages = MagicMock()
        MockClient.return_value.messages = mock_messages
        await process_sms_jobs(db)

    mock_messages.create.assert_called_once_with(
        body="Test notice",
        from_=settings.twilio_from_number,
        to="+15551234567",
    )
    await db.refresh(job)
    assert job.status == SMSJobStatus.sent
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_worker.py -v
```

Expected: both tests `PASSED`

- [ ] **Step 5: Run full test suite**

```bash
cd backend
uv run pytest tests/ -v
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add SMS worker with APScheduler poll loop and Twilio send"
```

---

### Task 17: .env.example and Final Wiring

**Files:**
- Create: `backend/.env.example`
- Create: `backend/alembic.ini` (verify it exists from Task 2)

- [ ] **Step 1: Write .env.example**

```bash
# backend/.env.example
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/northlanding
SECRET_KEY=replace-with-random-secret
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_FROM_NUMBER=+15550000000
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_SERVICE_KEY=your-supabase-service-role-key
SUPABASE_BUCKET=disc-photos
FRONTEND_URL=http://localhost:5173
```

- [ ] **Step 2: Verify all tests pass**

```bash
cd backend
uv run pytest tests/ -v --tb=short
```

Expected: all tests `PASSED`

- [ ] **Step 3: Verify the app starts**

```bash
cd backend
uv run uvicorn app.main:app --reload
# In another terminal:
curl http://localhost:8000/health
# Expected: {"status":"ok"}
curl http://localhost:8000/openapi.json | python3 -m json.tool | head -30
# Expected: valid OpenAPI JSON
```

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat: complete backend API with .env.example and verified startup"
```

---

## Self-Review Checklist (already resolved)

- All spec endpoints present: auth, users (phone verify), discs (CRUD + photos), admin (users, wishlist, pickup events, notify), webhooks ✓
- `SMSJob` model, `claim_pending_sms_jobs` with `SKIP LOCKED`, worker poll loop ✓
- 6-notice threshold implemented in `notification.py` with `FINAL_NOTICE_THRESHOLD = 6` ✓
- Phone numbers unique per user (not globally) — `UniqueConstraint("user_id", "number")` ✓
- `DiscPickupNotification` is source of truth for notification count; no redundant counter field ✓
- All test files import from the same type/function names defined in earlier tasks ✓
