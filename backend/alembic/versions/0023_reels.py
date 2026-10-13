"""Add Reel post type and media asset linkage.

Revision ID: 0023_reels
Revises: 0022_institution_discovery
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0023_reels"
down_revision: Union[str, None] = "0022_institution_discovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("post_type", sa.String(length=8), server_default="POST", nullable=False),
    )
    op.add_column(
        "posts",
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_posts_post_type", "posts", "post_type IN ('POST', 'REEL')"
    )
    op.create_check_constraint(
        "ck_posts_reel_media_asset",
        "posts",
        "(post_type = 'POST' AND media_asset_id IS NULL) OR "
        "(post_type = 'REEL' AND media_asset_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_posts_media_asset_id_media_assets",
        "posts",
        "media_assets",
        ["media_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_posts_type_created_at", "posts", ["post_type", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_posts_type_created_at", table_name="posts")
    op.drop_constraint("fk_posts_media_asset_id_media_assets", "posts", type_="foreignkey")
    op.drop_constraint("ck_posts_reel_media_asset", "posts", type_="check")
    op.drop_constraint("ck_posts_post_type", "posts", type_="check")
    op.drop_column("posts", "media_asset_id")
    op.drop_column("posts", "post_type")