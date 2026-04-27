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
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_clear: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    input_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_found: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_returned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    final_notice_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["Owner | None"] = relationship(back_populates="discs")
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
