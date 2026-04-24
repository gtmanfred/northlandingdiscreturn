from sqlalchemy.ext.asyncio import AsyncSession
from app.models.owner import Owner
from app.repositories.owner import OwnerRepository
from app.repositories.pickup_event import PickupEventRepository


HEADS_UP_TEMPLATE = (
    "Hi {name}, this is North Landing Disc Return. We found one of your discs. "
    "We'll text you again when we schedule a pickup event — these happen every "
    "1-2 months. Reply STOP to opt out."
)


async def maybe_enqueue_heads_up(
    *, owner: Owner, is_found: bool, db: AsyncSession
) -> bool:
    """Enqueue the one-time intro SMS to this owner. Returns True if enqueued."""
    if not is_found:
        return False
    if owner.heads_up_sent_at is not None:
        return False
    message = HEADS_UP_TEMPLATE.format(name=owner.name)
    await PickupEventRepository(db).create_sms_job(
        phone_number=owner.phone_number, message=message
    )
    await OwnerRepository(db).mark_heads_up_sent(owner)
    return True
