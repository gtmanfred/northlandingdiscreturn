"""add_sms_opt_out_and_skipped_status

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE smsjobstatus ADD VALUE IF NOT EXISTS 'skipped'")

    op.create_table(
        'sms_opt_out',
        sa.Column('id', PG_UUID(as_uuid=True), primary_key=True),
        sa.Column('phone_number', sa.String(), nullable=False),
        sa.Column(
            'opted_out_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint('phone_number', name='uq_sms_opt_out_phone_number'),
    )
    op.create_index('ix_sms_opt_out_phone_number', 'sms_opt_out', ['phone_number'])


def downgrade() -> None:
    op.drop_index('ix_sms_opt_out_phone_number', table_name='sms_opt_out')
    op.drop_table('sms_opt_out')
    # Note: PostgreSQL cannot drop an enum value; 'skipped' is left in place.
