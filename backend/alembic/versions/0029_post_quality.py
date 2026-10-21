"""Add post attachments, replies, comment likes, and edit state.

Revision ID: 0029_post_quality
Revises: 0028_music_library
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0029_post_quality"
down_revision: Union[str, None] = "0028_music_library"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_purpose",
        "media_assets",
        "purpose IN ('PROFILE_IMAGE', 'POST_MEDIA', 'POST_IMAGE', 'COURSE_MEDIA', "
        "'REEL', 'VIDEO', 'AUDIO', 'MESSAGE_ATTACHMENT')",
    )
    op.add_column(
        "posts", sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("comments", sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_comments_parent_id_comments", "comments", "comments", ["parent_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_comments_parent_id", "comments", ["parent_id"])
    op.create_table(
        "post_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("alt_text", sa.String(200), nullable=False, server_default=""),
        sa.CheckConstraint("position BETWEEN 0 AND 3", name="ck_post_attachments_position"),
        sa.UniqueConstraint("post_id", "position", name="uq_post_attachments_position"),
    )
    op.create_table(
        "comment_likes",
        sa.Column("comment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("comment_likes")
    op.drop_table("post_attachments")
    op.drop_index("ix_comments_parent_id", table_name="comments")
    op.drop_constraint("fk_comments_parent_id_comments", "comments", type_="foreignkey")
    op.drop_column("comments", "parent_id")
    op.drop_column("posts", "edited")
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_purpose",
        "media_assets",
        "purpose IN ('PROFILE_IMAGE', 'POST_MEDIA', 'COURSE_MEDIA', 'REEL', 'VIDEO', 'AUDIO', 'MESSAGE_ATTACHMENT')",
    )