import uuid
from datetime import datetime
from pydantic import BaseModel, computed_field


class OwnerOut(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    phone_number: str
    heads_up_sent_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
