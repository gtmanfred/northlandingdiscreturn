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
