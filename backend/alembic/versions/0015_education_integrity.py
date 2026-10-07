"""Enforce education institution and grading invariants in PostgreSQL.

Revision ID: 0015_education_integrity
Revises: 0014_privacy_membership_requests
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0015_education_integrity"
down_revision: Union[str, None] = "0014_privacy_membership_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION enforce_enrollment_institution_match() RETURNS trigger AS $$
        DECLARE student_institution uuid; course_institution uuid;
        BEGIN
            SELECT institution_id INTO student_institution FROM students WHERE id = NEW.student_id;
            SELECT f.institution_id INTO course_institution
            FROM courses c JOIN departments d ON d.id = c.department_id
            JOIN faculties f ON f.id = d.faculty_id WHERE c.id = NEW.course_id;
            IF student_institution IS NULL OR course_institution IS NULL
               OR student_institution <> course_institution THEN
                RAISE EXCEPTION 'enrollment student and course must belong to the same institution'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_enrollments_same_institution';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_enrollments_same_institution BEFORE INSERT OR UPDATE OF student_id, course_id "
        "ON enrollments FOR EACH ROW EXECUTE FUNCTION enforce_enrollment_institution_match()"
    )
    op.execute(
        """
        CREATE FUNCTION enforce_course_teacher_institution_match() RETURNS trigger AS $$
        DECLARE teacher_institution uuid; course_institution uuid;
        BEGIN
            SELECT institution_id INTO teacher_institution FROM teachers WHERE id = NEW.teacher_id;
            SELECT f.institution_id INTO course_institution
            FROM courses c JOIN departments d ON d.id = c.department_id
            JOIN faculties f ON f.id = d.faculty_id WHERE c.id = NEW.course_id;
            IF teacher_institution IS NULL OR course_institution IS NULL
               OR teacher_institution <> course_institution THEN
                RAISE EXCEPTION 'course teacher and course must belong to the same institution'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_course_teachers_same_institution';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_course_teachers_same_institution BEFORE INSERT OR UPDATE OF teacher_id, course_id "
        "ON course_teachers FOR EACH ROW EXECUTE FUNCTION enforce_course_teacher_institution_match()"
    )
    op.execute(
        """
        CREATE FUNCTION enforce_exercise_submission_institution_match() RETURNS trigger AS $$
        DECLARE student_institution uuid; exercise_institution uuid;
        BEGIN
            SELECT institution_id INTO student_institution FROM students WHERE id = NEW.student_id;
            SELECT f.institution_id INTO exercise_institution
            FROM exercises e JOIN lessons l ON l.id = e.lesson_id
            JOIN courses c ON c.id = l.course_id
            JOIN departments d ON d.id = c.department_id
            JOIN faculties f ON f.id = d.faculty_id WHERE e.id = NEW.exercise_id;
            IF student_institution IS NULL OR exercise_institution IS NULL
               OR student_institution <> exercise_institution THEN
                RAISE EXCEPTION 'exercise submission student and exercise must belong to the same institution'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_exercise_submissions_same_institution';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_exercise_submissions_same_institution BEFORE INSERT OR UPDATE OF student_id, exercise_id "
        "ON exercise_submissions FOR EACH ROW EXECUTE FUNCTION enforce_exercise_submission_institution_match()"
    )
    op.execute(
        """
        CREATE FUNCTION enforce_assessment_submission_institution_match() RETURNS trigger AS $$
        DECLARE student_institution uuid; assessment_institution uuid;
        BEGIN
            SELECT institution_id INTO student_institution FROM students WHERE id = NEW.student_id;
            SELECT f.institution_id INTO assessment_institution
            FROM assessments a JOIN courses c ON c.id = a.course_id
            JOIN departments d ON d.id = c.department_id
            JOIN faculties f ON f.id = d.faculty_id WHERE a.id = NEW.assessment_id;
            IF student_institution IS NULL OR assessment_institution IS NULL
               OR student_institution <> assessment_institution THEN
                RAISE EXCEPTION 'assessment submission student and assessment must belong to the same institution'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_assessment_submissions_same_institution';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_assessment_submissions_same_institution BEFORE INSERT OR UPDATE OF student_id, assessment_id "
        "ON assessment_submissions FOR EACH ROW EXECUTE FUNCTION enforce_assessment_submission_institution_match()"
    )
    op.execute(
        """
        CREATE FUNCTION enforce_lesson_progress_institution_match() RETURNS trigger AS $$
        DECLARE student_institution uuid; lesson_institution uuid;
        BEGIN
            SELECT institution_id INTO student_institution FROM students WHERE id = NEW.student_id;
            SELECT f.institution_id INTO lesson_institution
            FROM lessons l JOIN courses c ON c.id = l.course_id
            JOIN departments d ON d.id = c.department_id
            JOIN faculties f ON f.id = d.faculty_id WHERE l.id = NEW.lesson_id;
            IF student_institution IS NULL OR lesson_institution IS NULL
               OR student_institution <> lesson_institution THEN
                RAISE EXCEPTION 'lesson progress student and lesson must belong to the same institution'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_lesson_progress_same_institution';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_lesson_progress_same_institution BEFORE INSERT OR UPDATE OF student_id, lesson_id "
        "ON lesson_progress FOR EACH ROW EXECUTE FUNCTION enforce_lesson_progress_institution_match()"
    )
    op.execute(
        """
        CREATE FUNCTION enforce_assessment_result_max_score() RETURNS trigger AS $$
        DECLARE assessment_max numeric;
        BEGIN
            SELECT a.max_score INTO assessment_max
            FROM assessment_submissions s JOIN assessments a ON a.id = s.assessment_id
            WHERE s.id = NEW.submission_id FOR UPDATE OF a;
            IF assessment_max IS NULL OR NEW.score > assessment_max THEN
                RAISE EXCEPTION 'assessment result score exceeds assessment maximum'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_assessment_results_max_score';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_assessment_results_max_score BEFORE INSERT OR UPDATE OF submission_id, score "
        "ON assessment_results FOR EACH ROW EXECUTE FUNCTION enforce_assessment_result_max_score()"
    )
    op.execute(
        """
        CREATE FUNCTION enforce_assessment_max_score_update() RETURNS trigger AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM assessment_results r
                JOIN assessment_submissions s ON s.id = r.submission_id
                WHERE s.assessment_id = NEW.id AND r.score > NEW.max_score
            ) THEN
                RAISE EXCEPTION 'assessment maximum cannot be lower than an existing result'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_assessments_existing_result_max_score';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_assessments_existing_result_max_score BEFORE UPDATE OF max_score "
        "ON assessments FOR EACH ROW EXECUTE FUNCTION enforce_assessment_max_score_update()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_assessments_existing_result_max_score ON assessments")
    op.execute("DROP FUNCTION enforce_assessment_max_score_update()")
    op.execute("DROP TRIGGER trg_assessment_results_max_score ON assessment_results")
    op.execute("DROP FUNCTION enforce_assessment_result_max_score()")
    op.execute("DROP TRIGGER trg_lesson_progress_same_institution ON lesson_progress")
    op.execute("DROP FUNCTION enforce_lesson_progress_institution_match()")
    op.execute("DROP TRIGGER trg_assessment_submissions_same_institution ON assessment_submissions")
    op.execute("DROP FUNCTION enforce_assessment_submission_institution_match()")
    op.execute("DROP TRIGGER trg_exercise_submissions_same_institution ON exercise_submissions")
    op.execute("DROP FUNCTION enforce_exercise_submission_institution_match()")
    op.execute("DROP TRIGGER trg_course_teachers_same_institution ON course_teachers")
    op.execute("DROP FUNCTION enforce_course_teacher_institution_match()")
    op.execute("DROP TRIGGER trg_enrollments_same_institution ON enrollments")
    op.execute("DROP FUNCTION enforce_enrollment_institution_match()")