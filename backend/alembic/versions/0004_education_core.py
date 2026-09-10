"""Create the Education Core schema.

Revision ID: 0004_education_core
Revises: 0003_communication_core
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_education_core"
down_revision: Union[str, None] = "0003_communication_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps(table: str) -> None:
    op.create_index(f"ix_{table}_created_at", table, ["created_at"])


def upgrade() -> None:
    op.create_table(
        "institutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("institution_type", sa.String(length=30), nullable=False),
        sa.Column("website", sa.String(length=2048), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_institutions_name_not_blank"),
        sa.CheckConstraint("institution_type IN ('SCHOOL', 'UNIVERSITY', 'TRAINING_CENTER', 'MUSIC_SCHOOL', 'OTHER')", name="ck_institutions_type"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_institutions_name", "institutions", ["name"])

    op.create_table(
        "faculties",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_faculties_name_not_blank"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("institution_id", "name", name="uq_faculties_institution_name"),
    )
    op.create_index("ix_faculties_institution_id", "faculties", ["institution_id"])

    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("faculty_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_departments_name_not_blank"),
        sa.ForeignKeyConstraint(["faculty_id"], ["faculties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("faculty_id", "name", name="uq_departments_faculty_name"),
    )
    op.create_index("ix_departments_faculty_id", "departments", ["faculty_id"])

    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(code)) > 0", name="ck_courses_code_not_blank"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_courses_name_not_blank"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("department_id", "code", name="uq_courses_department_code"),
    )
    op.create_index("ix_courses_department_id", "courses", ["department_id"])
    op.create_index("ix_courses_code", "courses", ["code"])

    op.create_table(
        "teachers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "institution_id", name="uq_teachers_user_institution"),
    )
    op.create_index("ix_teachers_user_id", "teachers", ["user_id"])
    op.create_index("ix_teachers_institution_id", "teachers", ["institution_id"])

    op.create_table(
        "students",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "institution_id", name="uq_students_user_institution"),
    )
    op.create_index("ix_students_user_id", "students", ["user_id"])
    op.create_index("ix_students_institution_id", "students", ["institution_id"])

    op.create_table(
        "enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "course_id", name="uq_enrollments_student_course"),
    )
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])
    op.create_index("ix_enrollments_course_id", "enrollments", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_enrollments_course_id", table_name="enrollments")
    op.drop_index("ix_enrollments_student_id", table_name="enrollments")
    op.drop_table("enrollments")
    op.drop_index("ix_students_institution_id", table_name="students")
    op.drop_index("ix_students_user_id", table_name="students")
    op.drop_table("students")
    op.drop_index("ix_teachers_institution_id", table_name="teachers")
    op.drop_index("ix_teachers_user_id", table_name="teachers")
    op.drop_table("teachers")
    op.drop_index("ix_courses_code", table_name="courses")
    op.drop_index("ix_courses_department_id", table_name="courses")
    op.drop_table("courses")
    op.drop_index("ix_departments_faculty_id", table_name="departments")
    op.drop_table("departments")
    op.drop_index("ix_faculties_institution_id", table_name="faculties")
    op.drop_table("faculties")
    op.drop_index("ix_institutions_name", table_name="institutions")
    op.drop_table("institutions")
