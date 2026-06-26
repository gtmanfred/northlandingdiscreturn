import io
from dataclasses import dataclass
from datetime import date, datetime
import openpyxl
from app.phone import normalize_phone

SHEET_NAME = "Current"
HEADER_KEYWORD = "Name"


@dataclass
class ParsedDiscRow:
    row_number: int
    first_name: str
    last_name: str
    phone: str | None
    manufacturer: str
    model: str
    colors: list[str]
    notes: str | None
    input_date: date | None
    returned: bool
    returned_date: date | None
    error: str | None = None


def _split_name(raw) -> tuple[str, str]:
    text = (str(raw).strip() if raw is not None else "")
    if text in ("", "?"):
        return "", ""
    parts = text.split()
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], " ".join(parts[1:])


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def parse_current_sheet(file_bytes: bytes) -> list[ParsedDiscRow]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    if SHEET_NAME not in wb.sheetnames:
        raise ValueError("Current sheet not found")
    ws = wb[SHEET_NAME]
    grid = list(ws.iter_rows(values_only=True))

    header_idx = next(
        (i for i, r in enumerate(grid)
         if r and r[0] and HEADER_KEYWORD in str(r[0])),
        None,
    )
    if header_idx is None:
        raise ValueError("Header row not found in Current sheet")

    rows: list[ParsedDiscRow] = []
    for offset, r in enumerate(grid[header_idx + 1:], start=header_idx + 2):
        cells = list(r) + [None] * (10 - len(r))
        name, phone, mfr, model, color, other, code, found, returned_dt, _ = cells[:10]

        mfr = (str(mfr).strip() if mfr else "")
        model = (str(model).strip() if model else "")
        if not mfr and not model:
            continue  # blank row

        first, last = _split_name(name)
        phone_norm = None
        if phone:
            try:
                phone_norm = normalize_phone(str(phone))
            except ValueError:
                phone_norm = None

        colors = [c.lower() for c in str(color).split()] if color else []
        input_date = _as_date(found)
        ret_date = _as_date(returned_dt)
        code_str = (str(code).strip().upper() if code else "")
        returned = ret_date is not None or code_str == "R"
        if returned and ret_date is None:
            ret_date = input_date

        error = None
        if input_date is None:
            error = "missing or invalid Date found"

        rows.append(ParsedDiscRow(
            row_number=offset,
            first_name=first,
            last_name=last,
            phone=phone_norm,
            manufacturer=mfr,
            model=model,
            colors=colors,
            notes=(str(other).strip() if other else None),
            input_date=input_date,
            returned=returned,
            returned_date=ret_date if returned else None,
            error=error,
        ))
    return rows
