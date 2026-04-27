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

    # 6. Dedup: backfilling can collapse rows that had differing `name`
    #    whitespace into the same (first, last, phone) triple. Keep the
    #    oldest row in each group, repoint its discs, and drop the rest
    #    so we can add the unique constraint.
    #
    #    asyncpg can't run a multi-statement string in a prepared
    #    statement, so each step is its own op.execute call. The TEMP
    #    table is session-scoped and persists across executes inside the
    #    migration's single transaction.
    op.execute(
        """
        CREATE TEMP TABLE owner_keepers AS
        SELECT DISTINCT ON (first_name, last_name, phone_number)
            id, first_name, last_name, phone_number
        FROM owners
        ORDER BY first_name, last_name, phone_number, created_at, id
        """
    )
    op.execute(
        """
        UPDATE discs
        SET owner_id = k.id
        FROM owners o
        JOIN owner_keepers k
          ON o.first_name = k.first_name
         AND o.last_name = k.last_name
         AND o.phone_number = k.phone_number
        WHERE discs.owner_id = o.id
          AND o.id <> k.id
        """
    )
    op.execute(
        "DELETE FROM owners WHERE id NOT IN (SELECT id FROM owner_keepers)"
    )
    op.execute("DROP TABLE owner_keepers")

    # 7. Re-add uniqueness on the new triple.
    op.create_unique_constraint(
        "uq_owners_first_last_phone",
        "owners",
        ["first_name", "last_name", "phone_number"],
    )

    # 8. Disc notes column.
    op.add_column("discs", sa.Column("notes", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("discs", "notes")
    op.drop_constraint("uq_owners_first_last_phone", "owners", type_="unique")
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
