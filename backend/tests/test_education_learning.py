import uuid
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.models import Assessment, AssessmentResult, AssessmentSubmission, Course, Exercise, ExerciseSubmission, Lesson, LessonProgress, Student, Teacher, User
from app.routes.education_learning import (
    assign_teacher,
    create_assessment,
    create_lesson,
    create_submission,
    create_result,
    delete_assessment,
    delete_exercise,
    delete_lesson,
    get_course_progress,
    update_assessment,
    update_progress,
    update_submission,
)
from app.schemas import AssessmentCreate, AssessmentUpdate, CourseTeacherCreate, LessonCreate, LessonProgressUpdate, SubmissionCreate, SubmissionUpdate


class Result:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class LearningSession:
    def __init__(self, scalar_values=None, scalar_rows=None):
        self.scalar_values = list(scalar_values or [])
        self.scalar_rows = list(scalar_rows or [])
        self.added = []
        self.statements = []
        self.committed = False

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, statement):
        self.statements.append(statement)
        return Result(self.scalar_rows.pop(0) if self.scalar_rows else [])

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True
        now = datetime.now(timezone.utc)
        for value in self.added:
            if hasattr(value, "id") and value.id is None:
                value.id = uuid.uuid4()
            for field in ("created_at", "updated_at"):
                if hasattr(value, field) and getattr(value, field) is None:
                    setattr(value, field, now)

    async def refresh(self, _value):
        return None

    async def rollback(self):
        return None

    async def delete(self, _value):
        return None


class EducationLearningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = User(id=uuid.uuid4(), username="teacher", email="teacher@example.com", password_hash="hash")
        self.student_user = User(id=uuid.uuid4(), username="student", email="student@example.com", password_hash="hash")
        self.course = Course(id=uuid.uuid4(), department_id=uuid.uuid4(), code="CS101", name="Programming")
        self.teacher = Teacher(id=uuid.uuid4(), user_id=self.user.id, institution_id=uuid.uuid4())
        self.student = Student(id=uuid.uuid4(), user_id=self.student_user.id, institution_id=uuid.uuid4())
        self.lesson = Lesson(id=uuid.uuid4(), course_id=self.course.id, title="Intro", content="Content", position=0, is_published=True)
        self.assessment = Assessment(id=uuid.uuid4(), course_id=self.course.id, title="Quiz", instructions="Answer", max_score=Decimal("10.00"), is_published=True)

    async def test_assigned_teacher_creates_lesson_and_non_teacher_is_forbidden(self):
        session = LearningSession([self.teacher])
        created = await create_lesson(self.course.id, LessonCreate(title="Lesson", content="Body"), self.user, session)
        self.assertEqual(created["course_id"], str(self.course.id))
        teacher_query = str(session.statements[0].compile()).lower()
        self.assertIn("institution_memberships.role", teacher_query)
        self.assertIn("users.is_active", teacher_query)
        with self.assertRaises(HTTPException) as error:
            await create_lesson(self.course.id, LessonCreate(title="Denied", content="Body"), self.student_user, LearningSession([None]))
        self.assertEqual(error.exception.status_code, 403)

    async def test_lesson_schema_rejects_negative_position_and_blank_content(self):
        with self.assertRaises(ValidationError):
            LessonCreate(title="Lesson", content="Body", position=-1)
        with self.assertRaises(ValidationError):
            LessonCreate(title="Lesson", content="   ")

    async def test_course_teacher_assignment_requires_matching_institution_and_identity(self):
        admin_membership = type("Membership", (), {"id": uuid.uuid4(), "user_id": self.user.id, "institution_id": self.teacher.institution_id, "role": "ADMIN"})()
        assigned = await assign_teacher(self.course.id, CourseTeacherCreate(teacher_id=str(self.teacher.id)), self.user, LearningSession([self.teacher.institution_id, admin_membership, self.teacher]))
        self.assertEqual(assigned["teacher_id"], str(self.teacher.id))
        with self.assertRaises(HTTPException) as error:
            await assign_teacher(self.course.id, CourseTeacherCreate(teacher_id=str(self.teacher.id)), self.user, LearningSession([self.teacher.institution_id, None, self.teacher]))
        self.assertEqual(error.exception.status_code, 403)
        with self.assertRaises(HTTPException) as error:
            await assign_teacher(self.course.id, CourseTeacherCreate(teacher_id=str(uuid.uuid4())), self.user, LearningSession([self.teacher.institution_id, admin_membership, None]))
        self.assertEqual(error.exception.status_code, 404)

    async def test_published_assessment_submission_uses_authenticated_student(self):
        session = LearningSession([self.assessment, self.student])
        submission = await create_submission(self.assessment.id, SubmissionCreate(answer_text="answer"), self.student_user, session)
        self.assertEqual(submission["student_id"], str(self.student.id))
        student_query = str(session.statements[1].compile()).lower()
        self.assertIn("institution_memberships.role", student_query)
        self.assertIn("users.is_active", student_query)
        with self.assertRaises(HTTPException) as error:
            await create_submission(self.assessment.id, SubmissionCreate(answer_text="answer"), self.user, LearningSession([self.assessment, None]))
        self.assertEqual(error.exception.status_code, 403)

    async def test_due_assessment_rejects_late_submission(self):
        due = Assessment(id=uuid.uuid4(), course_id=self.course.id, title="Quiz", instructions="Answer", max_score=Decimal("10.00"), is_published=True, due_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        session = LearningSession([due, self.student])
        with self.assertRaises(HTTPException) as error:
            await create_submission(due.id, SubmissionCreate(answer_text="late"), self.student_user, session)
        self.assertEqual(error.exception.status_code, 422)
        student_query = str(session.statements[1].compile()).lower()
        self.assertIn("institution_memberships.role", student_query)
        self.assertIn("users.is_active", student_query)

    async def test_students_cannot_mark_assessments_graded_or_submit_drafts_late(self):
        with self.assertRaises(ValidationError):
            SubmissionCreate(answer_text="answer", status="GRADED")

        draft = AssessmentSubmission(
            id=uuid.uuid4(),
            assessment_id=self.assessment.id,
            student_id=self.student.id,
            answer_text="draft",
            status="DRAFT",
        )
        late_assessment = Assessment(
            id=self.assessment.id,
            course_id=self.course.id,
            title="Quiz",
            instructions="Answer",
            max_score=Decimal("10.00"),
            is_published=True,
            due_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        with self.assertRaises(HTTPException) as error:
            await update_submission(
                draft.id,
                SubmissionUpdate(status="SUBMITTED"),
                self.student_user,
                LearningSession([draft, self.student, late_assessment, self.student]),
            )
        self.assertEqual(error.exception.status_code, 422)

    async def test_teacher_cannot_grade_a_draft_assessment_submission(self):
        draft = AssessmentSubmission(
            id=uuid.uuid4(),
            assessment_id=self.assessment.id,
            student_id=self.student.id,
            status="DRAFT",
        )
        with self.assertRaises(HTTPException) as error:
            await create_result(
                draft.id,
                type("ResultInput", (), {"score": Decimal("1"), "feedback": None})(),
                self.user,
                LearningSession([draft, self.assessment, self.teacher]),
            )
        self.assertEqual(error.exception.status_code, 409)

    async def test_existing_learning_records_block_parent_deletion_and_score_invalidation(self):
        exercise = Exercise(id=uuid.uuid4(), lesson_id=self.lesson.id, title="Exercise", instructions="Do it", exercise_type="WRITTEN")
        attempt = ExerciseSubmission(id=uuid.uuid4(), exercise_id=exercise.id, student_id=self.student.id, attempt_number=1, answer_text="answer")
        with self.assertRaises(HTTPException) as exercise_error:
            await delete_exercise(
                exercise.id,
                self.user,
                LearningSession([exercise, self.lesson, self.teacher, attempt.id]),
            )
        self.assertEqual(exercise_error.exception.status_code, 409)

        progress = LessonProgress(id=uuid.uuid4(), student_id=self.student.id, lesson_id=self.lesson.id)
        with self.assertRaises(HTTPException) as lesson_error:
            await delete_lesson(
                self.lesson.id,
                self.user,
                LearningSession([self.lesson, self.teacher, progress.id]),
            )
        self.assertEqual(lesson_error.exception.status_code, 409)

        with self.assertRaises(HTTPException) as assessment_delete_error:
            await delete_assessment(
                self.assessment.id,
                self.user,
                LearningSession([self.assessment, self.teacher, uuid.uuid4()]),
            )
        self.assertEqual(assessment_delete_error.exception.status_code, 409)

        with self.assertRaises(HTTPException) as score_error:
            await update_assessment(
                self.assessment.id,
                AssessmentUpdate(max_score=Decimal("5.00")),
                self.user,
                LearningSession([self.assessment, self.teacher, uuid.uuid4()]),
            )
        self.assertEqual(score_error.exception.status_code, 409)

    async def test_submitted_assessment_answer_must_remain_nonblank(self):
        draft = AssessmentSubmission(
            id=uuid.uuid4(), assessment_id=self.assessment.id, student_id=self.student.id,
            answer_text="draft", status="DRAFT",
        )
        with self.assertRaises(HTTPException) as error:
            await update_submission(
                draft.id,
                SubmissionUpdate(answer_text=None, status="SUBMITTED"),
                self.student_user,
                LearningSession([draft, self.student, self.assessment, self.student]),
            )
        self.assertEqual(error.exception.status_code, 422)

    async def test_progress_upsert_is_safe_for_concurrent_first_completion(self):
        progress = LessonProgress(
            id=uuid.uuid4(),
            student_id=self.student.id,
            lesson_id=self.lesson.id,
            completed=True,
            completed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session = LearningSession([self.lesson, self.student, progress])
        response = await update_progress(
            self.lesson.id,
            LessonProgressUpdate(completed=True),
            self.student_user,
            session,
        )
        self.assertEqual(response["id"], str(progress.id))
        sql = str(session.statements[-1].compile(dialect=postgresql.dialect()))
        self.assertIn("ON CONFLICT (student_id, lesson_id) DO UPDATE", sql)

    async def test_result_rejects_score_above_maximum(self):
        submission = AssessmentSubmission(id=uuid.uuid4(), assessment_id=self.assessment.id, student_id=self.student.id, status="SUBMITTED")
        with self.assertRaises(HTTPException) as error:
            await create_result(submission.id, type("ResultInput", (), {"score": Decimal("11"), "feedback": None})(), self.user, LearningSession([submission, self.assessment, self.teacher]))
        self.assertEqual(error.exception.status_code, 422)

    async def test_progress_requires_enrollment_and_computes_zero_safely(self):
        with self.assertRaises(HTTPException) as error:
            await update_progress(self.lesson.id, LessonProgressUpdate(), self.student_user, LearningSession([self.lesson, None]))
        self.assertEqual(error.exception.status_code, 403)
        with self.assertRaises(HTTPException) as error:
            await get_course_progress(self.course.id, self.student_user, LearningSession([self.course, None]))
        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
