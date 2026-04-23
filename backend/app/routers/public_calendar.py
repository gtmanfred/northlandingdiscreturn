from typing import Annotated
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.pickup_event import PickupEventRepository
from app.services.pickup_calendar import build_ics_feed

router = APIRouter()


@router.get("/pickup-events.ics", include_in_schema=False)
async def pickup_events_ics(db: Annotated[AsyncSession, Depends(get_db)]) -> Response:
    repo = PickupEventRepository(db)
    events = await repo.list_published_events()
    body = build_ics_feed(events)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="pickup-events.ics"',
            "Cache-Control": "public, max-age=300",
        },
    )
