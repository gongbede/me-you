"""Add institution access and avatar references for stored media.

Revision ID: 0017_media_storage
Revises: 0016_account_email_tokens
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0017_media_storage"
down_revision: Union[str, None] = "0016_account_email_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_media_assets_institution_id_institutions",
        "media_assets",
        "institutions",
        ["institution_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_media_assets_institution_status",
        "media_assets",
        ["institution_id", "status"],
    )
    op.add_column(
        "profiles",
        sa.Column("avatar_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_profiles_avatar_asset_id_media_assets",
        "profiles",
        "media_assets",
        ["avatar_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_profiles_avatar_asset_id", "profiles", ["avatar_asset_id"])


def downgrade() -> None:
    op.drop_index("ix_profiles_avatar_asset_id", table_name="profiles")
    op.drop_constraint(
        "fk_profiles_avatar_asset_id_media_assets", "profiles", type_="foreignkey"
    )
    op.drop_column("profiles", "avatar_asset_id")
    op.drop_index("ix_media_assets_institution_status", table_name="media_assets")
    op.drop_constraint(
        "fk_media_assets_institution_id_institutions",
        "media_assets",
        type_="foreignkey",
    )
    op.drop_column("media_assets", "institution_id")