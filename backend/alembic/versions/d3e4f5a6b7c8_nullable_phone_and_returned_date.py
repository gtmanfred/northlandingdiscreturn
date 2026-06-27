"""nullable owner phone and disc returned_date

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("owners", "phone_number", existing_type=sa.String(), nullable=True)
    op.add_column("discs", sa.Column("returned_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("discs", "returned_date")
    op.execute("UPDATE owners SET phone_number = '' WHERE phone_number IS NULL")
    op.alter_column("owners", "phone_number", existing_type=sa.String(), nullable=False)
