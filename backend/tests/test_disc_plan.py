from datetime import date as _date
from sqlalchemy import select
from app.services.disc_import import (
    ParsedDiscRow, plan_import, apply_import, row_to_dict, row_from_dict,
)
from app.repositories.disc import DiscRepository
from app.models.disc import Disc
from app.models.pickup_event import SMSJob


def _row(**kw):
    base = dict(
        row_number=4, first_name="Jane", last_name="Doe", phone="+15551234567",
        manufacturer="Innova", model="Teebird", colors=["white"], notes="x",
        input_date=_date(2026, 6, 1), returned=False, returned_date=None, error=None,
    )
    base.update(kw)
    return ParsedDiscRow(**base)


def test_row_dict_round_trip():
    r = _row(returned=True, returned_date=_date(2026, 6, 5))
    r2 = row_from_dict(row_to_dict(r))
    assert r2 == r


async def test_plan_classifies_created(db):
    plan = await plan_import([_row()], db)
    d = plan.to_dict()
    assert d["counts"]["created"] == 1
    assert d["counts"]["updated"] == 0
    assert d["created"][0]["model"] == "Teebird"
    assert d["created"][0]["owner"] is not None


async def test_plan_makes_no_writes_and_no_sms(db):
    await plan_import([_row()], db)
    discs = (await db.execute(select(Disc))).scalars().all()
    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert len(discs) == 0
    assert len(jobs) == 0


async def test_plan_classifies_updated_with_diffs(db):
    await apply_import([_row()], db)
    plan = await plan_import([_row(notes="changed")], db)
    d = plan.to_dict()
    assert d["counts"]["updated"] == 1
    diff = d["updated"][0]["diffs"]
    assert {"field": "notes", "old": "x", "new": "changed"} in diff


async def test_plan_classifies_unchanged(db):
    await apply_import([_row()], db)
    plan = await plan_import([_row()], db)
    assert plan.to_dict()["counts"]["unchanged"] == 1


async def test_plan_classifies_owner_removal_as_updated(db):
    # Existing disc has an owner with a name but NO phone.
    await apply_import(
        [_row(first_name="Jane", last_name="Doe", phone=None)], db
    )
    # Re-imported row matches the same disc (find_by_import_key matches a
    # blank phone against an owner with no phone) but has no name/phone at
    # all, so apply_import would strip the owner. The plan must surface this
    # as an update with an owner diff to None, not classify it unchanged.
    plan = await plan_import(
        [_row(first_name="", last_name="", phone=None)], db
    )
    d = plan.to_dict()
    assert d["counts"]["updated"] == 1
    assert d["counts"]["unchanged"] == 0
    diff = d["updated"][0]["diffs"]
    owner_diffs = [x for x in diff if x["field"] == "owner"]
    assert len(owner_diffs) == 1
    assert owner_diffs[0]["new"] is None


async def test_plan_captures_error_rows_full_content(db):
    plan = await plan_import([_row(error="missing or invalid Date found", input_date=None)], db)
    d = plan.to_dict()
    assert d["counts"]["errors"] == 1
    err = d["errors"][0]
    assert err["reason"] == "missing or invalid Date found"
    assert err["row"]["manufacturer"] == "Innova"
    assert err["row"]["model"] == "Teebird"


async def test_plan_created_will_notify_when_phone_and_not_returned(db):
    plan = await plan_import([_row(phone="+15551234567", returned=False)], db)
    d = plan.to_dict()
    item = d["created"][0]
    assert item["will_notify"] is True
    assert item["skip_reason"] is None
    assert d["counts"]["will_notify"] == 1


async def test_plan_created_returned_does_not_notify(db):
    plan = await plan_import(
        [_row(phone="+15551234567", returned=True, returned_date=_date(2026, 6, 5))], db
    )
    item = plan.to_dict()["created"][0]
    assert item["will_notify"] is False
    assert item["skip_reason"] == "returned"
    assert plan.to_dict()["counts"]["will_notify"] == 0


async def test_plan_created_no_phone_does_not_notify(db):
    plan = await plan_import([_row(phone=None)], db)
    item = plan.to_dict()["created"][0]
    assert item["will_notify"] is False
    assert item["skip_reason"] == "no phone"
