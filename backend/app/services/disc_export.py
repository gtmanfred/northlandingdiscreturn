import io
from openpyxl import Workbook

DISC_EXPORT_COLUMNS = [
    "Name", "Phone", "Mfr", "Model", "Color", "Other",
    "Code", "Date found", "Date returned", "Date contacted",
]

TITLE = "North Landing Discs Database"

DATE_COLUMNS = {"Date found", "Date returned", "Date contacted"}


def build_current_sheet_workbook(rows: list[dict]) -> bytes:
    """Build an .xlsx mirroring the Current sheet layout. Returns the file bytes."""
    wb = Workbook(iso_dates=True)  # iso_dates=True makes openpyxl store Python date objects as real date cells (not datetime), so they round-trip correctly on re-import
    ws = wb.active
    ws.title = "Current"
    ws.append([TITLE])
    ws.append(DISC_EXPORT_COLUMNS)
    for row in rows:
        ws.append([row.get(col) for col in DISC_EXPORT_COLUMNS])
    # Apply date number format to date columns
    date_col_indices = {
        col_idx for col_idx, name in enumerate(DISC_EXPORT_COLUMNS, start=1)
        if name in DATE_COLUMNS
    }
    for row in ws.iter_rows(min_row=3):
        for cell in row:
            if cell.column in date_col_indices and cell.value is not None:
                cell.number_format = "yyyy-mm-dd"
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
