import io
from datetime import date
import openpyxl
from app.services.disc_export import build_current_sheet_workbook, DISC_EXPORT_COLUMNS


def test_columns_order():
    assert DISC_EXPORT_COLUMNS == [
        "Name", "Phone", "Mfr", "Model", "Color", "Other",
        "Code", "Date found", "Date returned", "Date contacted",
    ]


def test_build_workbook_roundtrip():
    rows = [{
        "Name": "Jane Doe", "Phone": "+15551234567", "Mfr": "Innova",
        "Model": "Teebird", "Color": "white", "Other": "no prev",
        "Code": "", "Date found": date(2026, 6, 1),
        "Date returned": None, "Date contacted": date(2026, 6, 3),
    }]
    data = build_current_sheet_workbook(rows)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    grid = list(ws.iter_rows(values_only=True))
    header = grid[1]
    assert list(header) == DISC_EXPORT_COLUMNS
    first = dict(zip(header, grid[2]))
    assert first["Name"] == "Jane Doe"
    assert first["Date found"] == date(2026, 6, 1)
    assert first["Date returned"] is None
    assert first["Date contacted"] == date(2026, 6, 3)
