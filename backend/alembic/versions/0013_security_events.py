"""Add security audit events.

Revision ID: 0013_security_events
Revises: 0012_rate_limit_counters
Create Date: 2026-10-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0013_security_events"
down_revision: Union[str, None] = "0012_rate_limit_counters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=8), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("outcome IN ('SUCCESS', 'FAILURE')", name="ck_security_events_outcome"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_events_occurred_at", "security_events", ["occurred_at"])
    op.create_index("ix_security_events_institution_id", "security_events", ["institution_id"])
    op.create_index("ix_security_events_actor_user_id", "security_events", ["actor_user_id"])


def downgrade() -> None:
    op.drop_index("ix_security_events_actor_user_id", table_name="security_events")
    op.drop_index("ix_security_events_institution_id", table_name="security_events")
    op.drop_index("ix_security_events_occurred_at", table_name="security_events")
    op.drop_table("security_events")