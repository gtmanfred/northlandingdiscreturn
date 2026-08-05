"""Stamp stable ids into the Current sheet's ID column.

One-off reconciliation. Reads the database, writes only the spreadsheet: a row
that resolves to an existing disc gets that disc's real uuid, an unresolved row
gets a fresh uuid so the next import creates it with a stable identity. A cell
that already holds something is never touched.
"""

import io
import uuid
from dataclasses import dataclass, field

import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.disc import DiscRepository
from app.services.disc_import import (
    DUPLICATE_ID_ERROR,
    FORMULA_ID_ERROR,
    ID_COLUMN_NUMBER,
    INVALID_ID_ERROR,
    SHEET_NAME,
    parse_current_sheet,
)

ID_ERRORS = {INVALID_ID_ERROR, FORMULA_ID_ERROR, DUPLICATE_ID_ERROR}


@dataclass
class BackfillReport:
    already_populated: int = 0
    matched: int = 0
    generated: int = 0
    skipped: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "already_populated": self.already_populated,
            "matched": self.matched,
            "generated": self.generated,
            "skipped": self.skipped,
        }


async def backfill_ids(
    file_bytes: bytes,
    db: AsyncSession,
    *,
    dry_run: bool = False,
) -> tuple[bytes | None, BackfillReport]:
    rows = parse_current_sheet(file_bytes)
    disc_repo = DiscRepository(db)
    report = BackfillReport()

    # data_only=False keeps every other cell's formula intact on save.
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
    ws = wb[SHEET_NAME]

    claimed: set[uuid.UUID] = set()

    for row in rows:
        if row.disc_id is not None:
            report.already_populated += 1
            claimed.add(row.disc_id)

    writes: list[tuple[int, str]] = []

    for row in rows:
        if row.disc_id is not None:
            continue
        if row.error in ID_ERRORS:
            report.skipped.append({"row": row.row_number, "reason": row.error})
            continue

        existing = None
        if row.input_date is not None:
            existing = await disc_repo.find_by_import_key(
                input_date=row.input_date,
                manufacturer=row.manufacturer,
                name=row.model,
                colors=row.colors,
                phone=row.phone,
            )

        if existing is None:
            new_id = uuid.uuid4()
            report.generated += 1
        elif existing.id in claimed:
            report.skipped.append({
                "row": row.row_number,
                "reason": f"resolved disc {existing.id} already claimed by an earlier row",
            })
            continue
        else:
            new_id = existing.id
            report.matched += 1

        claimed.add(new_id)
        writes.append((row.row_number, str(new_id)))

    if dry_run:
        return None, report

    for row_number, value in writes:
        ws.cell(row=row_number, column=ID_COLUMN_NUMBER, value=value)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue(), report
