import io
from dataclasses import dataclass, field
from datetime import date, datetime
import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession
from app.phone import normalize_phone
from app.repositories.disc import DiscRepository
from app.repositories.owner import OwnerRepository

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


@dataclass
class ImportSummary:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)


async def import_rows(rows: list[ParsedDiscRow], db: AsyncSession) -> ImportSummary:
    summary = ImportSummary()
    disc_repo = DiscRepository(db)
    owner_repo = OwnerRepository(db)

    for row in rows:
        if row.error or row.input_date is None:
            summary.errors.append({"row": row.row_number, "reason": row.error or "no date found"})
            continue

        owner_id = None
        if row.phone or row.first_name or row.last_name:
            owner = await owner_repo.resolve_or_create(
                first_name=row.first_name,
                last_name=row.last_name,
                phone_number=row.phone,
            )
            owner_id = owner.id

        existing = await disc_repo.find_by_import_key(
            input_date=row.input_date,
            manufacturer=row.manufacturer,
            name=row.model,
            colors=row.colors,
            phone=row.phone,
        )

        if existing is None:
            disc = await disc_repo.create(
                manufacturer=row.manufacturer,
                name=row.model,
                colors=row.colors,
                input_date=row.input_date,
                owner_id=owner_id,
                notes=row.notes,
            )
            if row.returned:
                await disc_repo.update(
                    disc, is_returned=True, returned_date=row.returned_date
                )
            summary.created += 1
        else:
            updates = {}
            if (existing.notes or None) != (row.notes or None):
                updates["notes"] = row.notes
            if [c.strip().lower() for c in existing.colors] != [c.strip().lower() for c in row.colors]:
                updates["colors"] = row.colors
            if existing.owner_id != owner_id:
                updates["owner_id"] = owner_id
            # one-way return: only ever set returned, never clear
            if row.returned and not existing.is_returned:
                updates["is_returned"] = True
                updates["returned_date"] = row.returned_date
            if updates:
                await disc_repo.update(existing, **updates)
                summary.updated += 1
            else:
                summary.skipped += 1

    await db.flush()
    return summary
