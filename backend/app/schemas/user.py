# backend/app/schemas/user.py
import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator
from app.phone import normalize_phone


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
    number: str

    @field_validator("number")
    @classmethod
    def normalize(cls, v: str) -> str:
        return normalize_phone(v)


class VerifyPhoneRequest(BaseModel):
    number: str
    code: str

    @field_validator("number")
    @classmethod
    def normalize(cls, v: str) -> str:
        return normalize_phone(v)


class UpdateUserRequest(BaseModel):
    name: str | None = None
    is_admin: bool | None = None
