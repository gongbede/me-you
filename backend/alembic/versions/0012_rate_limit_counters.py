"""Add shared PostgreSQL rate-limit counters.

Revision ID: 0012_rate_limit_counters
Revises: 0011_media_assets
Create Date: 2026-10-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_rate_limit_counters"
down_revision: Union[str, None] = "0011_media_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("scope", "key_hash", "window_start"),
        sa.CheckConstraint("count > 0", name="ck_rate_limit_counters_count_positive"),
        sa.CheckConstraint("window_seconds > 0", name="ck_rate_limit_counters_window_positive"),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_counters")