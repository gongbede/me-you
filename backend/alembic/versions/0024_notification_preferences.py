"""Add per-user notification preferences.

Revision ID: 0024_notification_preferences
Revises: 0023_reels
Create Date: 2026-10-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0024_notification_preferences"
down_revision: Union[str, None] = "0023_reels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "notification_type"),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
