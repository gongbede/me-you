"""Add student exercise attempts and teacher feedback.

Revision ID: 0008_exercise_submissions
Revises: 0007_platform_infrastructure
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0008_exercise_submissions"
down_revision: Union[str, None] = "0007_platform_infrastructure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exercise_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_number > 0", name="ck_exercise_submissions_attempt_positive"),
        sa.CheckConstraint("length(btrim(answer_text)) > 0", name="ck_exercise_submissions_answer_not_blank"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exercise_id", "student_id", "attempt_number", name="uq_exercise_submissions_attempt"),
    )
    op.create_index("ix_exercise_submissions_exercise_id", "exercise_submissions", ["exercise_id"])
    op.create_index("ix_exercise_submissions_student_id", "exercise_submissions", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_exercise_submissions_student_id", table_name="exercise_submissions")
    op.drop_index("ix_exercise_submissions_exercise_id", table_name="exercise_submissions")
    op.drop_table("exercise_submissions")