import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import Base


class Owner(Base):
    __tablename__ = "owners"
    __table_args__ = (
        UniqueConstraint("name", "phone_number", name="uq_owners_name_phone"),
        Index("ix_owners_phone_number", "phone_number"),
        Index("ix_owners_name", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone_number: Mapped[str] = mapped_column(String, nullable=False)
    heads_up_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # discs relationship added in Task 3 when Disc.owner is defined
