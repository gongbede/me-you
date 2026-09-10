"""Create the Social Core schema.

Revision ID: 0002_social_core
Revises: 0001_initial_schema
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_social_core"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(content)) > 0", name="ck_posts_content_not_blank"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_posts_author_created_at", "posts", ["author_id", "created_at"]
    )

    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(content)) > 0", name="ck_comments_content_not_blank"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_comments_post_created_at", "comments", ["post_id", "created_at"]
    )

    op.create_table(
        "post_likes",
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("post_id", "user_id"),
    )
    op.create_index(
        "ix_post_likes_post_created_at", "post_likes", ["post_id", "created_at"]
    )

    op.create_table(
        "follows",
        sa.Column("follower_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("following_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("follower_id <> following_id", name="ck_follows_not_self"),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["following_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("follower_id", "following_id"),
    )
    op.create_index("ix_follows_following_id", "follows", ["following_id"])

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("comment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "type IN ('LIKE', 'COMMENT', 'FOLLOW')",
            name="ck_notifications_type",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["comment_id"], ["comments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_recipient_created_at",
        "notifications",
        ["recipient_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_created_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_follows_following_id", table_name="follows")
    op.drop_table("follows")
    op.drop_index("ix_post_likes_post_created_at", table_name="post_likes")
    op.drop_table("post_likes")
    op.drop_index("ix_comments_post_created_at", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_posts_author_created_at", table_name="posts")
    op.drop_table("posts")
