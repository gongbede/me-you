"""Create the Education Learning Core schema.

Revision ID: 0005_education_learning_core
Revises: 0004_education_core
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_education_learning_core"
down_revision: Union[str, None] = "0004_education_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "course_teachers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "teacher_id", name="uq_course_teachers_course_teacher"),
    )
    op.create_index("ix_course_teachers_course_id", "course_teachers", ["course_id"])
    op.create_index("ix_course_teachers_teacher_id", "course_teachers", ["teacher_id"])

    op.create_table(
        "lessons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_lessons_title_not_blank"),
        sa.CheckConstraint("length(btrim(content)) > 0", name="ck_lessons_content_not_blank"),
        sa.CheckConstraint("position >= 0", name="ck_lessons_position_non_negative"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lessons_course_position", "lessons", ["course_id", "position"])

    op.create_table(
        "exercises",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("exercise_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_exercises_title_not_blank"),
        sa.CheckConstraint("length(btrim(instructions)) > 0", name="ck_exercises_instructions_not_blank"),
        sa.CheckConstraint("position >= 0", name="ck_exercises_position_non_negative"),
        sa.CheckConstraint("exercise_type IN ('PRACTICE', 'WRITTEN', 'PROJECT', 'OTHER')", name="ck_exercises_type"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exercises_lesson_position", "exercises", ["lesson_id", "position"])

    op.create_table(
        "assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("max_score", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_assessments_title_not_blank"),
        sa.CheckConstraint("length(btrim(instructions)) > 0", name="ck_assessments_instructions_not_blank"),
        sa.CheckConstraint("max_score > 0", name="ck_assessments_max_score_positive"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assessments_course_published", "assessments", ["course_id", "is_published"])

    op.create_table(
        "assessment_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'SUBMITTED', 'GRADED')", name="ck_submissions_status"),
        sa.CheckConstraint("status = 'DRAFT' OR length(btrim(answer_text)) > 0", name="ck_submissions_answer_when_submitted"),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "student_id", name="uq_submissions_assessment_student"),
    )
    op.create_index("ix_submissions_assessment_id", "assessment_submissions", ["assessment_id"])
    op.create_index("ix_submissions_student_id", "assessment_submissions", ["student_id"])

    op.create_table(
        "assessment_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Numeric(10, 2), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score >= 0", name="ck_results_score_non_negative"),
        sa.ForeignKeyConstraint(["submission_id"], ["assessment_submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", name="uq_results_submission"),
    )
    op.create_index("ix_results_submission_id", "assessment_results", ["submission_id"])

    op.create_table(
        "lesson_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "lesson_id", name="uq_lesson_progress_student_lesson"),
    )
    op.create_index("ix_lesson_progress_student_id", "lesson_progress", ["student_id"])
    op.create_index("ix_lesson_progress_lesson_id", "lesson_progress", ["lesson_id"])


def downgrade() -> None:
    op.drop_index("ix_lesson_progress_lesson_id", table_name="lesson_progress")
    op.drop_index("ix_lesson_progress_student_id", table_name="lesson_progress")
    op.drop_table("lesson_progress")
    op.drop_index("ix_results_submission_id", table_name="assessment_results")
    op.drop_table("assessment_results")
    op.drop_index("ix_submissions_student_id", table_name="assessment_submissions")
    op.drop_index("ix_submissions_assessment_id", table_name="assessment_submissions")
    op.drop_table("assessment_submissions")
    op.drop_index("ix_assessments_course_published", table_name="assessments")
    op.drop_table("assessments")
    op.drop_index("ix_exercises_lesson_position", table_name="exercises")
    op.drop_table("exercises")
    op.drop_index("ix_lessons_course_position", table_name="lessons")
    op.drop_table("lessons")
    op.drop_index("ix_course_teachers_teacher_id", table_name="course_teachers")
    op.drop_index("ix_course_teachers_course_id", table_name="course_teachers")
    op.drop_table("course_teachers")
