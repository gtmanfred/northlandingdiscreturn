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


def test_missing_current_sheet_raises():
    wb = openpyxl.Workbook()
    wb.active.title = "Other"
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError):
        parse_current_sheet(buf.getvalue())
