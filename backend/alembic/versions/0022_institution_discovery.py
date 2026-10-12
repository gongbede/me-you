"""Add opt-in institution discovery fields.

Revision ID: 0022_institution_discovery
Revises: 0021_live_classrooms
Create Date: 2026-10-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0022_institution_discovery"
down_revision: Union[str, None] = "0021_live_classrooms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "institutions",
        sa.Column("public_description", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "institutions",
        sa.Column("is_listed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index(
        "ix_institutions_listed_name",
        "institutions",
        ["is_listed", "name"],
    )


def downgrade() -> None:
    op.drop_index("ix_institutions_listed_name", table_name="institutions")
    op.drop_column("institutions", "is_listed")
    op.drop_column("institutions", "public_description")