"""Stamp stable disc ids into the Current sheet's ID column (column K).

Usage (from repo root):
    export DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/dbname'
    uv run --project backend python scripts/backfill_disc_ids.py discs.xlsx --dry-run
    uv run --project backend python scripts/backfill_disc_ids.py discs.xlsx

Reads the database, writes only the spreadsheet. A row that resolves to an
existing disc gets that disc's real uuid; an unresolved row gets a fresh uuid.
A cell that already holds a value is never touched, so re-running is safe.

Back the file up first: openpyxl rewrites the whole workbook on save and does
not preserve charts, images, or pivot tables.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.services.disc_id_backfill import backfill_ids  # noqa: E402


def normalize_database_url(url: str) -> str:
    """asyncpg needs the +asyncpg driver marker; accept a plain psql URL too."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


async def run(*, xlsx_path: Path, output: Path, database_url: str, dry_run: bool) -> int:
    engine = create_async_engine(normalize_database_url(database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            data, report = await backfill_ids(
                xlsx_path.read_bytes(), db, dry_run=dry_run
            )
            await db.rollback()  # read-only by contract; make it explicit
    finally:
        await engine.dispose()

    print(json.dumps(report.as_dict(), indent=2))
    if dry_run:
        print("(dry-run: spreadsheet not written)")
        return 0

    output.write_bytes(data)
    print(f"wrote {output}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("xlsx_path", type=Path)
    p.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Postgres URL. Default: $DATABASE_URL.",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--output",
        type=Path,
        help="Where to write the result. Default: overwrite xlsx_path.",
    )
    args = p.parse_args()

    if not args.xlsx_path.exists():
        print(f"file not found: {args.xlsx_path}", file=sys.stderr)
        return 2
    if not args.database_url:
        print(
            "error: database URL required (set $DATABASE_URL or pass --database-url)",
            file=sys.stderr,
        )
        return 2

    return asyncio.run(
        run(
            xlsx_path=args.xlsx_path,
            output=args.output or args.xlsx_path,
            database_url=args.database_url,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
