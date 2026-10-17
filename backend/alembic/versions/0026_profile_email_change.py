"""Add follower-only profiles and email-change tokens.

Revision ID: 0026_profile_email_change
Revises: 0025_reports_blocks_moderation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0026_profile_email_change"
down_revision: Union[str, None] = "0025_reports_blocks_moderation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_profiles_visibility", "profiles", type_="check")
    op.create_check_constraint(
        "ck_profiles_visibility",
        "profiles",
        "visibility IN ('PUBLIC', 'AUTHENTICATED', 'NETWORK', 'FOLLOWERS', 'PRIVATE')",
    )
    op.drop_constraint("ck_account_email_tokens_purpose", "account_email_tokens", type_="check")
    op.create_check_constraint(
        "ck_account_email_tokens_purpose",
        "account_email_tokens",
        "purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET', 'EMAIL_CHANGE')",
    )
    op.add_column(
        "account_email_tokens", sa.Column("pending_email", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("account_email_tokens", "pending_email")
    op.drop_constraint("ck_account_email_tokens_purpose", "account_email_tokens", type_="check")
    op.create_check_constraint(
        "ck_account_email_tokens_purpose",
        "account_email_tokens",
        "purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET')",
    )
    op.drop_constraint("ck_profiles_visibility", "profiles", type_="check")
    op.create_check_constraint(
        "ck_profiles_visibility",
        "profiles",
        "visibility IN ('PUBLIC', 'AUTHENTICATED', 'NETWORK', 'PRIVATE')",
    )
