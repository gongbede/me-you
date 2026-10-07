"""Add account deletion and email action token lifecycle fields.

Revision ID: 0016_account_email_tokens
Revises: 0015_education_integrity
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0016_account_email_tokens"
down_revision: Union[str, None] = "0015_education_integrity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "account_email_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET')",
            name="ck_account_email_tokens_purpose",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_account_email_tokens_hash"),
    )
    op.create_index(
        "ix_account_email_tokens_user_purpose",
        "account_email_tokens",
        ["user_id", "purpose", "consumed_at"],
    )
    op.create_index("ix_account_email_tokens_expiry", "account_email_tokens", ["expires_at"])
    op.create_index(
        "uq_account_email_tokens_active_user_purpose",
        "account_email_tokens",
        ["user_id", "purpose"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL"),
    )


def downgrade() -> None:
    has_lifecycle_data = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM account_email_tokens) "
            "OR EXISTS (SELECT 1 FROM users "
            "WHERE email_verified_at IS NOT NULL OR deleted_at IS NOT NULL)"
        )
    ).scalar_one()
    if has_lifecycle_data:
        raise RuntimeError(
            "Cannot downgrade account email token lifecycle while token or account lifecycle data exists"
        )
    op.drop_index(
        "uq_account_email_tokens_active_user_purpose",
        table_name="account_email_tokens",
    )
    op.drop_index("ix_account_email_tokens_expiry", table_name="account_email_tokens")
    op.drop_index("ix_account_email_tokens_user_purpose", table_name="account_email_tokens")
    op.drop_table("account_email_tokens")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "email_verified_at")