"""Add reports, user blocks, and reversible content hiding.

Revision ID: 0025_reports_blocks_moderation
Revises: 0024_notification_preferences
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0025_reports_blocks_moderation"
down_revision: Union[str, None] = "0024_notification_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "posts", sa.Column("is_hidden", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.add_column(
        "comments", sa.Column("is_hidden", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.create_index("ix_posts_is_hidden", "posts", ["is_hidden", "created_at"])
    op.create_index("ix_comments_is_hidden", "comments", ["is_hidden", "created_at"])

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("reporter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=8), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("details", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="OPEN", nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "target_type IN ('POST', 'COMMENT', 'REEL', 'USER', 'MESSAGE')",
            name="ck_reports_target_type",
        ),
        sa.CheckConstraint(
            "reason IN ('SPAM', 'HARASSMENT', 'INAPPROPRIATE', 'MISINFORMATION', 'OTHER')",
            name="ck_reports_reason",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'REVIEWED', 'DISMISSED', 'ACTIONED')",
            name="ck_reports_status",
        ),
    )
    op.create_index("ix_reports_status_created_at", "reports", ["status", "created_at"])
    op.create_index("ix_reports_target", "reports", ["target_type", "target_id"])
    op.create_index(
        "uq_reports_open_reporter_target",
        "reports",
        ["reporter_id", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
    )
    op.create_table(
        "user_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("blocker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("blocked_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_pair"),
        sa.CheckConstraint("blocker_id <> blocked_id", name="ck_user_blocks_not_self"),
    )
    op.create_index("ix_user_blocks_blocked_id", "user_blocks", ["blocked_id"])


def downgrade() -> None:
    op.drop_index("ix_user_blocks_blocked_id", table_name="user_blocks")
    op.drop_table("user_blocks")
    op.drop_index("uq_reports_open_reporter_target", table_name="reports")
    op.drop_index("ix_reports_target", table_name="reports")
    op.drop_index("ix_reports_status_created_at", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_comments_is_hidden", table_name="comments")
    op.drop_index("ix_posts_is_hidden", table_name="posts")
    op.drop_column("comments", "is_hidden")
    op.drop_column("posts", "is_hidden")
