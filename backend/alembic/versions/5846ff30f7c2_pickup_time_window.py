"""pickup time window

Revision ID: 5846ff30f7c2
Revises: faadcb5befeb
Create Date: 2026-04-23 12:18:18.473755

"""
from alembic import op
import sqlalchemy as sa


revision = "5846ff30f7c2"
down_revision = "faadcb5befeb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pickup_events",
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pickup_events",
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pickup_events",
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
    )

    # Backfill existing rows: 4pm-6pm America/New_York on scheduled_date
    op.execute(
        """
        UPDATE pickup_events
        SET
            start_at = ((scheduled_date::text || ' 16:00:00')::timestamp
                        AT TIME ZONE 'America/New_York'),
            end_at   = ((scheduled_date::text || ' 18:00:00')::timestamp
                        AT TIME ZONE 'America/New_York')
        WHERE start_at IS NULL
        """
    )

    op.alter_column("pickup_events", "start_at", nullable=False)
    op.alter_column("pickup_events", "end_at", nullable=False)
    op.drop_column("pickup_events", "scheduled_date")


def downgrade() -> None:
    op.add_column(
        "pickup_events",
        sa.Column("scheduled_date", sa.Date(), nullable=True),
    )
    op.execute(
        """
        UPDATE pickup_events
        SET scheduled_date = (start_at AT TIME ZONE 'America/New_York')::date
        """
    )
    op.alter_column("pickup_events", "scheduled_date", nullable=False)
    op.drop_column("pickup_events", "end_at")
    op.drop_column("pickup_events", "start_at")
    op.drop_column("pickup_events", "sequence")
