"""add_import_staging

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB


revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, Sequence[str], None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'import_staging',
        sa.Column('id', PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            'created_by', PG_UUID(as_uuid=True),
            sa.ForeignKey('users.id'), nullable=False,
        ),
        sa.Column('filename', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('rows', JSONB(), nullable=False),
        sa.Column('plan', JSONB(), nullable=False),
    )
    op.create_index('ix_import_staging_created_by', 'import_staging', ['created_by'])


def downgrade() -> None:
    op.drop_index('ix_import_staging_created_by', table_name='import_staging')
    op.drop_table('import_staging')
