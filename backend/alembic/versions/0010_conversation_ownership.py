"""Persist group conversation ownership.

Revision ID: 0010_conversation_ownership
Revises: 0009_account_security
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010_conversation_ownership"
down_revision: Union[str, None] = "0009_account_security"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_created_by_id_users",
        "conversations",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_conversations_created_by_id", "conversations", ["created_by_id"])
    op.execute(
        "UPDATE conversations AS conversation "
        "SET created_by_id = (SELECT member.user_id FROM conversation_members AS member "
        "WHERE member.conversation_id = conversation.id "
        "ORDER BY member.joined_at, member.user_id LIMIT 1) "
        "WHERE conversation.type = 'GROUP' AND conversation.created_by_id IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_created_by_id", table_name="conversations")
    op.drop_constraint("fk_conversations_created_by_id_users", "conversations", type_="foreignkey")
    op.drop_column("conversations", "created_by_id")