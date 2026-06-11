from sqlalchemy.ext.asyncio import AsyncSession
from app.models.disc import Disc
from app.models.owner import Owner
from app.repositories.pickup_event import PickupEventRepository


HEADS_UP_TEMPLATE = (
    "Hi {name}, this is North Landing Disc Return. We found one of your discs: "
    "{disc_desc}. View it and get pickup details at https://discreturn.nl. "
    "Questions or comments? Email nldiscman@gmail.com. "
    "Reply STOP to opt out."
)


async def maybe_enqueue_heads_up(*, owner: Owner, disc: Disc, db: AsyncSession) -> bool:
    """Enqueue a found-disc SMS to this owner, once per found disc. Returns True if enqueued."""
    if not disc.is_found:
        return False
    disc_desc = f"{disc.manufacturer} {disc.name} ({disc.color})"
    message = HEADS_UP_TEMPLATE.format(name=owner.name, disc_desc=disc_desc)
    await PickupEventRepository(db).create_sms_job(
        phone_number=owner.phone_number, message=message
    )
    return True
