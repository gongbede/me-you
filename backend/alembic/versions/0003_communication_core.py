"""Create the Communication Core schema.

Revision ID: 0003_communication_core
Revises: 0002_social_core
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_communication_core"
down_revision: Union[str, None] = "0002_social_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.create_check_constraint("ck_notifications_type", "notifications", "type IN ('LIKE', 'COMMENT', 'FOLLOW', 'MESSAGE')")

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("direct_key", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("type IN ('DIRECT', 'GROUP')", name="ck_conversations_type"),
        sa.CheckConstraint("type = 'GROUP' OR direct_key IS NOT NULL", name="ck_conversations_direct_key"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("direct_key"),
    )
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"])

    op.create_table(
        "conversation_members",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("conversation_id", "user_id"),
    )
    op.create_index("ix_conversation_members_user_id", "conversation_members", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(btrim(content)) > 0", name="ck_messages_content_not_blank"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_created_at", "messages", ["conversation_id", "created_at"])
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])


def downgrade() -> None:
    message_notifications = op.get_bind().execute(
        sa.text("SELECT count(*) FROM notifications WHERE type = 'MESSAGE'")
    ).scalar_one()
    if message_notifications:
        raise RuntimeError(
            "Cannot downgrade Communication Core while MESSAGE notifications exist"
        )
    op.drop_index("ix_messages_sender_id", table_name="messages")
    op.drop_index("ix_messages_conversation_created_at", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversation_members_user_id", table_name="conversation_members")
    op.drop_table("conversation_members")
    op.drop_index("ix_conversations_updated_at", table_name="conversations")
    op.drop_table("conversations")
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.create_check_constraint("ck_notifications_type", "notifications", "type IN ('LIKE', 'COMMENT', 'FOLLOW')")
