"""Add reusable notifications, activity records, and indexes.

Revision ID: 0007_platform_infrastructure
Revises: 0006_institution_memberships
Create Date: 2026-10-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007_platform_infrastructure"
down_revision: Union[str, None] = "0006_institution_memberships"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.alter_column(
        "notifications",
        "type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.add_column("notifications", sa.Column("title", sa.String(length=200), nullable=True))
    op.add_column("notifications", sa.Column("payload", sa.JSON(), nullable=True))
    op.add_column("notifications", sa.Column("target_type", sa.String(length=80), nullable=True))
    op.add_column("notifications", sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        "UPDATE notifications SET title = CASE type "
        "WHEN 'LIKE' THEN 'New like' "
        "WHEN 'COMMENT' THEN 'New comment' "
        "WHEN 'FOLLOW' THEN 'New follower' "
        "WHEN 'MESSAGE' THEN 'New message' "
        "ELSE 'Notification' END WHERE title IS NULL"
    )
    op.alter_column("notifications", "title", existing_type=sa.String(length=200), nullable=False)
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["recipient_id", "read_at"],
    )

    op.create_table(
        "activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activities_actor_created_at", "activities", ["actor_id", "created_at"])
    op.create_index("ix_activities_target", "activities", ["target_type", "target_id"])
    op.create_index("ix_activities_event_created_at", "activities", ["event_type", "created_at"])


def downgrade() -> None:
    unsupported_types = op.get_bind().execute(
        sa.text(
            "SELECT DISTINCT type FROM notifications "
            "WHERE type NOT IN ('LIKE', 'COMMENT', 'FOLLOW')"
        )
    ).scalars().all()
    if unsupported_types:
        raise RuntimeError(
            "Cannot downgrade platform infrastructure while MESSAGE or extensible notification types exist"
        )

    op.drop_index("ix_activities_event_created_at", table_name="activities")
    op.drop_index("ix_activities_target", table_name="activities")
    op.drop_index("ix_activities_actor_created_at", table_name="activities")
    op.drop_table("activities")

    op.drop_index("ix_notifications_recipient_unread", table_name="notifications")
    op.drop_column("notifications", "target_id")
    op.drop_column("notifications", "target_type")
    op.drop_column("notifications", "payload")
    op.drop_column("notifications", "title")
    op.alter_column(
        "notifications",
        "type",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_notifications_type",
        "notifications",
        "type IN ('LIKE', 'COMMENT', 'FOLLOW', 'MESSAGE')",
    )
