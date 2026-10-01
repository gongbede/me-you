"""Add institution membership records for scoped administration.

Revision ID: 0006_institution_memberships
Revises: 0005_education_learning_core
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_institution_memberships"
down_revision: Union[str, None] = "0005_education_learning_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "institution_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('ADMIN', 'TEACHER', 'STUDENT')", name="ck_institution_memberships_role"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "institution_id", name="uq_institution_memberships_user_institution"),
    )
    op.create_index("ix_institution_memberships_user_id", "institution_memberships", ["user_id"])
    op.create_index("ix_institution_memberships_institution_id", "institution_memberships", ["institution_id"])


def downgrade() -> None:
    op.drop_index("ix_institution_memberships_institution_id", table_name="institution_memberships")
    op.drop_index("ix_institution_memberships_user_id", table_name="institution_memberships")
    op.drop_table("institution_memberships")
