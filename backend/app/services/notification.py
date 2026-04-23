# backend/app/services/notification.py
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.disc import DiscRepository
from app.repositories.pickup_event import PickupEventRepository
from app.models.pickup_event import PickupEvent
from app.core.timezone import COURSE_TIMEZONE


FINAL_NOTICE_THRESHOLD = 6


async def enqueue_pickup_notifications(
    event: PickupEvent, db: AsyncSession
) -> tuple[int, int]:
    """
    Returns (sms_jobs_enqueued, discs_notified).
    Composes SMS messages grouped by phone number and writes SMSJob rows.
    Does NOT call Twilio — the worker handles that.
    """
    disc_repo = DiscRepository(db)
    event_repo = PickupEventRepository(db)

    unreturned = await disc_repo.list_unreturned_found()
    notified_disc_count = 0
    phone_discs: dict[str, list] = defaultdict(list)
    phone_is_final: dict[str, bool] = defaultdict(bool)

    for disc in unreturned:
        if await event_repo.disc_already_notified_for_event(disc.id, event.id):
            continue
        prior_count = await event_repo.count_notifications_for_disc(disc.id)
        is_final = prior_count + 1 >= FINAL_NOTICE_THRESHOLD
        await event_repo.create_disc_notification(
            disc_id=disc.id, pickup_event_id=event.id, is_final_notice=is_final
        )
        if is_final:
            await disc_repo.update(disc, final_notice_sent=True)
            phone_is_final[disc.phone_number] = True
        phone_discs[disc.phone_number].append(disc)
        notified_disc_count += 1

    sms_count = 0
    local_start = event.start_at.astimezone(COURSE_TIMEZONE)
    local_end = event.end_at.astimezone(COURSE_TIMEZONE)
    window_str = (
        f"{local_start.strftime('%b %-d')} from "
        f"{local_start.strftime('%-I:%M %p')} to "
        f"{local_end.strftime('%-I:%M %p')} ET"
    )
    for phone_number, discs in phone_discs.items():
        disc_list = ", ".join(
            f"{d.manufacturer} {d.name} ({d.color})" for d in discs
        )
        if phone_is_final.get(phone_number):
            message = (
                f"FINAL NOTICE: Your disc(s) [{disc_list}] will be added to the "
                f"sale box if not picked up at the {window_str} pickup. "
                "Reply STOP to opt out."
            )
        else:
            message = (
                f"Disc pickup at North Landing {window_str}. "
                f"You have disc(s): {disc_list}. Reply STOP to opt out."
            )
        await event_repo.create_sms_job(phone_number=phone_number, message=message)
        sms_count += 1

    return sms_count, notified_disc_count
