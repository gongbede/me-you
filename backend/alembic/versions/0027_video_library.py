"""Add video library.

Revision ID: 0027_video_library
Revises: 0026_profile_email_change
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0027_video_library"
down_revision: Union[str, None] = "0026_profile_email_change"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_purpose", "media_assets",
        "purpose IN ('PROFILE_IMAGE', 'POST_MEDIA', 'COURSE_MEDIA', 'REEL', 'VIDEO', 'AUDIO', 'MESSAGE_ATTACHMENT')",
    )
    op.drop_constraint("ck_reports_target_type", "reports", type_="check")
    op.create_check_constraint(
        "ck_reports_target_type", "reports",
        "target_type IN ('POST', 'COMMENT', 'REEL', 'VIDEO', 'TRACK', 'USER', 'MESSAGE')",
    )
    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False, server_default=""),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(12), nullable=False, server_default="PUBLIC"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("visibility IN ('PUBLIC', 'FOLLOWERS', 'PRIVATE')", name="ck_videos_visibility"),
        sa.CheckConstraint("view_count >= 0", name="ck_videos_view_count"),
    )
    op.create_index("ix_videos_category_created", "videos", ["category", "created_at"])
    op.create_index("ix_videos_owner_created", "videos", ["owner_id", "created_at"])
    op.create_table(
        "video_likes",
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "video_views",
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("view_date", sa.Date(), primary_key=True),
    )
    op.create_table(
        "video_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_video_comments_video_created", "video_comments", ["video_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_video_comments_video_created", table_name="video_comments")
    op.drop_table("video_comments")
    op.drop_table("video_views")
    op.drop_table("video_likes")
    op.drop_index("ix_videos_owner_created", table_name="videos")
    op.drop_index("ix_videos_category_created", table_name="videos")
    op.drop_table("videos")
    op.drop_constraint("ck_reports_target_type", "reports", type_="check")
    op.create_check_constraint(
        "ck_reports_target_type", "reports",
        "target_type IN ('POST', 'COMMENT', 'REEL', 'USER', 'MESSAGE')",
    )
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_purpose", "media_assets",
        "purpose IN ('PROFILE_IMAGE', 'POST_MEDIA', 'COURSE_MEDIA', 'REEL', 'MESSAGE_ATTACHMENT')",
    )
