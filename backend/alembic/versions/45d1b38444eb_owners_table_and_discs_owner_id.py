"""owners table and discs.owner_id

Revision ID: 45d1b38444eb
Revises: 5846ff30f7c2
Create Date: 2026-04-24 19:40:24.740548

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = '45d1b38444eb'
down_revision: Union[str, Sequence[str], None] = '5846ff30f7c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create owners table
    op.create_table(
        "owners",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column("heads_up_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", "phone_number", name="uq_owners_name_phone"),
    )
    op.create_index("ix_owners_phone_number", "owners", ["phone_number"])
    op.create_index("ix_owners_name", "owners", ["name"])

    # 2. Add discs.owner_id
    op.add_column(
        "discs",
        sa.Column("owner_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_discs_owner_id",
        "discs",
        "owners",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_discs_owner_id", "discs", ["owner_id"])

    # 3. Backfill owners from existing discs (one row per distinct
    #    non-null (owner_name, phone_number) pair). heads_up_sent_at is
    #    set to the earliest disc.created_at for that pair, so existing
    #    owners are treated as already contacted.
    op.execute(
        """
        INSERT INTO owners (id, name, phone_number, heads_up_sent_at, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            owner_name,
            phone_number,
            MIN(created_at),
            MIN(created_at),
            NOW()
        FROM discs
        WHERE owner_name IS NOT NULL
          AND phone_number IS NOT NULL
        GROUP BY owner_name, phone_number
        """
    )

    # 4. Link discs to their owner row
    op.execute(
        """
        UPDATE discs
        SET owner_id = owners.id
        FROM owners
        WHERE discs.owner_name = owners.name
          AND discs.phone_number = owners.phone_number
        """
    )

    # 5. Drop the old freetext columns
    op.drop_column("discs", "owner_name")
    op.drop_column("discs", "phone_number")


def downgrade() -> None:
    op.add_column("discs", sa.Column("owner_name", sa.String(), nullable=True))
    op.add_column("discs", sa.Column("phone_number", sa.String(), nullable=True))

    op.execute(
        """
        UPDATE discs
        SET owner_name = owners.name,
            phone_number = owners.phone_number
        FROM owners
        WHERE discs.owner_id = owners.id
        """
    )

    op.drop_index("ix_discs_owner_id", table_name="discs")
    op.drop_constraint("fk_discs_owner_id", "discs", type_="foreignkey")
    op.drop_column("discs", "owner_id")
    op.drop_index("ix_owners_name", table_name="owners")
    op.drop_index("ix_owners_phone_number", table_name="owners")
    op.drop_table("owners")
