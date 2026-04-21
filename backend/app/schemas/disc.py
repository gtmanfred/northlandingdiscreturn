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
    phone_number: str
    owner_name: str | None = None


class DiscPage(BaseModel):
    items: list[DiscOut]
    page: int
    page_size: int
    total: int
