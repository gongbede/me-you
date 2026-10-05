"""Add revocable sessions, account status, platform roles, and login throttles.

Revision ID: 0009_account_security
Revises: 0008_exercise_submissions
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_account_security"
down_revision: Union[str, None] = "0008_exercise_submissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("users", sa.Column("is_platform_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "login_throttles",
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("failed_count >= 0", name="ck_login_throttles_failures_non_negative"),
        sa.PrimaryKeyConstraint("subject_hash"),
    )


def downgrade() -> None:
    op.drop_table("login_throttles")
    op.drop_column("users", "is_platform_admin")
    op.drop_column("users", "is_active")
    op.drop_column("users", "token_version")