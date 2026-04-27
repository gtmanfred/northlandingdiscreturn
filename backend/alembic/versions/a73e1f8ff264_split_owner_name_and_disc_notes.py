"""split owner name and disc notes

Revision ID: a73e1f8ff264
Revises: 485472f19d21
Create Date: 2026-04-27 13:24:06.684304

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a73e1f8ff264"
down_revision: Union[str, Sequence[str], None] = "485472f19d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the new owner name columns (nullable for backfill).
    op.add_column("owners", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column(
        "owners",
        sa.Column("last_name", sa.String(), nullable=False, server_default=""),
    )

    # 2. Backfill: split existing `name` on the first space.
    op.execute(
        """
        UPDATE owners
        SET
            first_name = CASE
                WHEN position(' ' in name) = 0 THEN name
                ELSE substring(name from 1 for position(' ' in name) - 1)
            END,
            last_name = CASE
                WHEN position(' ' in name) = 0 THEN ''
                ELSE trim(substring(name from position(' ' in name) + 1))
            END
        """
    )

    # 3. Lock first_name to NOT NULL after backfill.
    op.alter_column("owners", "first_name", nullable=False)

    # 4. Drop old uniqueness, name index, and the column itself.
    op.drop_constraint("uq_owners_name_phone", "owners", type_="unique")
    op.drop_index("ix_owners_name", table_name="owners")
    op.drop_column("owners", "name")

    # 5. New composite index for autocomplete / sorted listing.
    op.create_index(
        "ix_owners_last_first", "owners", ["last_name", "first_name"]
    )

    # 6. Disc notes column.
    op.add_column("discs", sa.Column("notes", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("discs", "notes")
    op.drop_index("ix_owners_last_first", table_name="owners")
    op.add_column("owners", sa.Column("name", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE owners
        SET name = CASE
            WHEN last_name = '' THEN first_name
            ELSE first_name || ' ' || last_name
        END
        """
    )
    op.alter_column("owners", "name", nullable=False)
    op.create_index("ix_owners_name", "owners", ["name"])
    op.create_unique_constraint(
        "uq_owners_name_phone", "owners", ["name", "phone_number"]
    )
    op.drop_column("owners", "last_name")
    op.drop_column("owners", "first_name")
