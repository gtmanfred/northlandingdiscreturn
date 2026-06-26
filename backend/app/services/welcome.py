from sqlalchemy.ext.asyncio import AsyncSession
from app.models.owner import Owner
from app.repositories.owner import OwnerRepository
from app.repositories.pickup_event import PickupEventRepository


WELCOME_TEMPLATE = (
    "Hi {name}, this is North Landing Disc Return — we reunite lost discs with "
    "their owners. To see what discs have been found and get pickup updates, go "
    "to https://discreturn.nl, sign up, and connect this phone number to your profile. "
    "This number isn't monitored for replies. Reply STOP to opt out."
)


async def maybe_enqueue_welcome(*, owner: Owner, db: AsyncSession) -> bool:
    """Enqueue the one-time welcome SMS to this owner. Returns True if enqueued."""
    if owner.welcome_sent_at is not None:
        return False
    message = WELCOME_TEMPLATE.format(name=owner.name)
    await PickupEventRepository(db).create_sms_job(
        phone_number=owner.phone_number, message=message
    )
    await OwnerRepository(db).mark_welcome_sent(owner)
    return True
