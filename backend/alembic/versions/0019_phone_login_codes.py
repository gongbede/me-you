"""Add one-time phone sign-in code storage.

Revision ID: 0019_phone_login_codes
Revises: 0018_auth_identities
Create Date: 2026-10-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0019_phone_login_codes"
down_revision: Union[str, None] = "0018_auth_identities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "phone_login_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone_number", sa.String(length=16), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 5",
            name="ck_phone_login_codes_attempts",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_number", name="uq_phone_login_codes_phone_number"),
    )
    op.create_index("ix_phone_login_codes_expires_at", "phone_login_codes", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_phone_login_codes_expires_at", table_name="phone_login_codes")
    op.drop_table("phone_login_codes")