"""Add course live classroom sessions, attendance, and messages.

Revision ID: 0021_live_classrooms
Revises: 0020_exercise_publication
Create Date: 2026-10-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0021_live_classrooms"
down_revision: Union[str, None] = "0020_exercise_publication"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "class_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="SCHEDULED", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_class_sessions_title_not_blank"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_class_sessions_end_after_start"),
        sa.CheckConstraint("status IN ('SCHEDULED', 'LIVE', 'ENDED', 'CANCELLED')", name="ck_class_sessions_status"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_class_sessions_course_start", "class_sessions", ["course_id", "starts_at"])
    op.create_table(
        "class_session_attendance",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=8), server_default="ABSENT", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("marked_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('PRESENT', 'LATE', 'ABSENT')", name="ck_class_session_attendance_status"),
        sa.ForeignKeyConstraint(["session_id"], ["class_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["marked_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("session_id", "user_id"),
    )
    op.create_index("ix_class_session_attendance_user", "class_session_attendance", ["user_id"])
    op.create_table(
        "class_session_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_type", sa.String(length=12), server_default="CHAT", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("message_type IN ('CHAT', 'ANNOUNCEMENT')", name="ck_class_session_messages_type"),
        sa.CheckConstraint("length(btrim(content)) > 0", name="ck_class_session_messages_content_not_blank"),
        sa.ForeignKeyConstraint(["session_id"], ["class_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_class_session_messages_session_created", "class_session_messages", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_class_session_messages_session_created", table_name="class_session_messages")
    op.drop_table("class_session_messages")
    op.drop_index("ix_class_session_attendance_user", table_name="class_session_attendance")
    op.drop_table("class_session_attendance")
    op.drop_index("ix_class_sessions_course_start", table_name="class_sessions")
    op.drop_table("class_sessions")