import uuid
from datetime import datetime
from pydantic import BaseModel


class OwnerOut(BaseModel):
    id: uuid.UUID
    name: str
    phone_number: str
    heads_up_sent_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
