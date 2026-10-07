"""Add explicit privacy and institution membership request state.

Revision ID: 0014_privacy_membership_requests
Revises: 0013_security_events
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0014_privacy_membership_requests"
down_revision: Union[str, None] = "0013_security_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("visibility", sa.String(length=16), server_default="NETWORK", nullable=False),
    )
    op.create_check_constraint(
        "ck_profiles_visibility", "profiles", "visibility IN ('PUBLIC', 'AUTHENTICATED', 'NETWORK', 'PRIVATE')"
    )
    op.add_column(
        "posts",
        sa.Column("visibility", sa.String(length=20), server_default="PUBLIC", nullable=False),
    )
    op.create_check_constraint(
        "ck_posts_visibility",
        "posts",
        "visibility IN ('PUBLIC', 'AUTHENTICATED', 'NETWORK', 'PRIVATE')",
    )
    op.create_table(
        "institution_membership_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("request_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('ADMIN', 'TEACHER', 'STUDENT')",
            name="ck_institution_membership_requests_role",
        ),
        sa.CheckConstraint(
            "(request_type = 'JOIN' AND status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'CANCELLED')) "
            "OR (request_type = 'INVITATION' AND status IN ('INVITED', 'ACCEPTED', 'REJECTED', 'CANCELLED'))",
            name="ck_institution_membership_requests_state",
        ),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_institution_membership_requests_institution_status_created",
        "institution_membership_requests",
        ["institution_id", "status", "created_at"],
    )
    op.create_index(
        "ix_institution_membership_requests_user_status_created",
        "institution_membership_requests",
        ["user_id", "status", "created_at"],
    )
    op.create_index(
        "uq_institution_membership_requests_open_user",
        "institution_membership_requests",
        ["institution_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('REQUESTED', 'INVITED')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_institution_membership_requests_open_user",
        table_name="institution_membership_requests",
    )
    op.drop_index(
        "ix_institution_membership_requests_user_status_created",
        table_name="institution_membership_requests",
    )
    op.drop_index(
        "ix_institution_membership_requests_institution_status_created",
        table_name="institution_membership_requests",
    )
    op.drop_table("institution_membership_requests")
    op.drop_constraint("ck_posts_visibility", "posts", type_="check")
    op.drop_column("posts", "visibility")
    op.drop_constraint("ck_profiles_visibility", "profiles", type_="check")
    op.drop_column("profiles", "visibility")