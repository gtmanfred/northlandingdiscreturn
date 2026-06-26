"""disc colors as ordered tag array

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-26 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the ordered tag array (nullable for backfill).
    op.add_column(
        "discs",
        sa.Column("colors", postgresql.ARRAY(sa.String()), nullable=True),
    )

    # 2. Backfill: split the old free-text color on commas/whitespace, trim,
    #    drop empty tokens, preserve original order via WITH ORDINALITY.
    op.execute(
        r"""
        UPDATE discs
        SET colors = COALESCE(
            (
                SELECT array_agg(tok ORDER BY ord)
                FROM unnest(
                    regexp_split_to_array(trim(color), '[,[:space:]]+')
                ) WITH ORDINALITY AS t(tok, ord)
                WHERE tok <> ''
            ),
            ARRAY[]::varchar[]
        )
        """
    )

    # 3. Enforce NOT NULL and drop the old column.
    op.alter_column("discs", "colors", nullable=False)
    op.drop_column("discs", "color")


def downgrade() -> None:
    op.add_column(
        "discs",
        sa.Column("color", sa.String(), nullable=False, server_default=""),
    )
    op.execute("UPDATE discs SET color = array_to_string(colors, ' ')")
    op.alter_column("discs", "color", server_default=None)
    op.drop_column("discs", "colors")
