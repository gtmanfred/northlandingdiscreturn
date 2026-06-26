import io
from datetime import date
import openpyxl
import pytest
from app.services.disc_import import parse_current_sheet, ParsedDiscRow


def _make_sheet(data_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Current"
    ws.append(["North Landing Discs Database"])
    ws.append(["Sorted by ...", None, None, None, None, None, "Code: ..."])
    ws.append(["Name", "Phone", "Mfr", "Model", "Color", "Other",
               "Code", "Date found", "Date retuned", "Date contacted"])
    for r in data_rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_basic_row():
    data = _make_sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple trans",
         "Ed no prev", None, date(2026, 6, 6), None, None],
    ])
    rows = parse_current_sheet(data)
    assert len(rows) == 1
    row = rows[0]
    assert row.first_name == "Jane"
    assert row.last_name == "Doe"
    assert row.phone == "+14049518881"
    assert row.manufacturer == "Discraft"
    assert row.model == "Heat"
    assert row.colors == ["purple", "trans"]
    assert row.notes == "Ed no prev"
    assert row.input_date == date(2026, 6, 6)
    assert row.returned is False
    assert row.error is None


def test_parse_returned_row_from_date():
    data = _make_sheet([
        ["?", None, "Innova", "Roc", "blue", "donate", None,
         date(2026, 1, 1), date(2026, 2, 1), None],
    ])
    row = parse_current_sheet(data)[0]
    assert row.first_name == ""
    assert row.last_name == ""
    assert row.phone is None
    assert row.returned is True
    assert row.returned_date == date(2026, 2, 1)


def test_parse_returned_row_from_code():
    data = _make_sheet([
        ["Sam", "404-353-5987", "Axiom", "Fireball", "pink", "x", "R",
         date(2026, 1, 1), None, None],
    ])
    row = parse_current_sheet(data)[0]
    assert row.returned is True
    assert row.returned_date == date(2026, 1, 1)  # falls back to date found


def test_missing_date_found_sets_error():
    data = _make_sheet([
        ["Sam", "404-353-5987", "Axiom", "Fireball", "pink", "x", None, None, None, None],
    ])
    row = parse_current_sheet(data)[0]
    assert row.error is not None


def test_code_mr_not_returned():
    data = _make_sheet([
        ["Sam", "404-353-5987", "Axiom", "Fireball", "pink", "x", "MR",
         date(2026, 1, 1), None, None],
    ])
    row = parse_current_sheet(data)[0]
    assert row.returned is False


def test_garbage_code_not_returned():
    data = _make_sheet([
        ["Sam", "404-353-5987", "Axiom", "Fireball", "pink", "x",
         "brvscr.searchtofind.net", date(2026, 1, 1), None, None],
    ])
    row = parse_current_sheet(data)[0]
    assert row.returned is False


def test_invalid_phone_is_none_no_raise():
    data = _make_sheet([
        ["Sam", "not-a-phone", "Axiom", "Fireball", "pink", "x", None,
         date(2026, 1, 1), None, None],
    ])
    row = parse_current_sheet(data)[0]
    assert row.phone is None


def test_missing_current_sheet_raises():
    wb = openpyxl.Workbook()
    wb.active.title = "Other"
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError):
        parse_current_sheet(buf.getvalue())


import pytest
from datetime import date as _date
from app.services.disc_import import import_rows, ParsedDiscRow, ImportSummary
from app.repositories.disc import DiscRepository


def _row(**kw):
    base = dict(
        row_number=4, first_name="Jane", last_name="Doe", phone="+15551234567",
        manufacturer="Innova", model="Teebird", colors=["white"], notes="x",
        input_date=_date(2026, 6, 1), returned=False, returned_date=None, error=None,
    )
    base.update(kw)
    return ParsedDiscRow(**base)


@pytest.mark.asyncio
async def test_import_creates_then_updates(db):
    s1 = await import_rows([_row()], db)
    assert s1.created == 1 and s1.updated == 0

    # same key, changed notes -> update, not create
    s2 = await import_rows([_row(notes="changed")], db)
    assert s2.created == 0 and s2.updated == 1

    repo = DiscRepository(db)
    rows = await repo.list_for_export()
    assert len(rows) == 1
    assert rows[0].notes == "changed"


@pytest.mark.asyncio
async def test_import_returned_is_one_way(db):
    await import_rows([_row()], db)
    repo = DiscRepository(db)
    disc = (await repo.list_for_export())[0]
    # mark returned in-app
    await repo.update(disc, is_returned=True, returned_date=_date(2026, 6, 5))
    await db.flush()
    # re-import the row still showing active -> must NOT un-return
    await import_rows([_row()], db)
    disc = (await repo.list_for_export())[0]
    assert disc.is_returned is True


@pytest.mark.asyncio
async def test_import_marks_returned_from_sheet(db):
    await import_rows([_row()], db)
    await import_rows([_row(returned=True, returned_date=_date(2026, 6, 9))], db)
    repo = DiscRepository(db)
    disc = (await repo.list_for_export())[0]
    assert disc.is_returned is True
    assert disc.returned_date == _date(2026, 6, 9)


@pytest.mark.asyncio
async def test_import_reports_row_errors(db):
    summary = await import_rows([_row(error="missing or invalid Date found")], db)
    assert summary.created == 0
    assert len(summary.errors) == 1
    assert summary.errors[0]["row"] == 4
