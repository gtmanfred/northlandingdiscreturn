# backend/app/schemas/disc.py
import uuid
from datetime import datetime, date
from pydantic import BaseModel, field_validator
from app.phone import normalize_phone
from app.schemas.owner import OwnerOut
from app.services.storage import storage_path_to_url
from pydantic import model_validator


class DiscPhotoOut(BaseModel):
    id: uuid.UUID
    photo_path: str
    sort_order: int

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def normalize_photo_path(self) -> "DiscPhotoOut":
        self.photo_path = storage_path_to_url(self.photo_path)
        return self


class DiscOut(BaseModel):
    id: uuid.UUID
    manufacturer: str
    name: str
    color: str
    owner: OwnerOut | None = None
    is_clear: bool
    input_date: date
    is_found: bool
    is_returned: bool
    final_notice_sent: bool
    notes: str | None = None
    photos: list[DiscPhotoOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscCreate(BaseModel):
    manufacturer: str
    name: str
    color: str
    input_date: date
    owner_first_name: str | None = None
    owner_last_name: str | None = None
    phone_number: str | None = None
    notes: str | None = None
    is_clear: bool = False
    is_found: bool = True

    @field_validator("phone_number")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        return normalize_phone(v) if v else None

    @model_validator(mode="after")
    def owner_fields_together(self) -> "DiscCreate":
        # All three owner fields are present-or-absent together. Empty-string
        # last_name is valid (single-token names) when first_name + phone are set.
        provided = (
            self.owner_first_name is not None,
            self.owner_last_name is not None,
            self.phone_number is not None,
        )
        if any(provided) and not all(provided):
            raise ValueError(
                "owner_first_name, owner_last_name, and phone_number must be "
                "provided together or not at all"
            )
        return self


class DiscUpdate(BaseModel):
    manufacturer: str | None = None
    name: str | None = None
    color: str | None = None
    owner_first_name: str | None = None
    owner_last_name: str | None = None
    phone_number: str | None = None
    notes: str | None = None
    is_clear: bool | None = None
    is_found: bool | None = None
    is_returned: bool | None = None

    @field_validator("phone_number")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        return normalize_phone(v) if v else None


class WishlistDiscCreate(BaseModel):
    manufacturer: str | None = None
    name: str | None = None
    color: str | None = None
    phone_number: str
    owner_first_name: str | None = None
    owner_last_name: str | None = None
    notes: str | None = None

    @field_validator("phone_number")
    @classmethod
    def normalize(cls, v: str) -> str:
        return normalize_phone(v)


class DiscPage(BaseModel):
    items: list[DiscOut]
    page: int
    page_size: int
    total: int
