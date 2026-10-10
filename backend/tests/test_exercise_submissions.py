import unittest
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.database import get_postgres_session
from app.models import Activity, Course, Exercise, ExerciseSubmission, Lesson, Notification, Student, Teacher, User
from app.routes.education_learning import (
    create_exercise_submission,
    get_exercise_submission,
    list_course_exercise_submissions,
    list_exercise_submissions,
    review_exercise_submission,
    router,
)
from app.schemas import ExerciseSubmissionCreate, ExerciseSubmissionReview


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class ExerciseSession:
    def __init__(self, scalar_values=None, scalar_rows=None, commit_error=None):
        self.scalar_values = list(scalar_values or [])
        self.scalar_rows = list(scalar_rows or [])
        self.commit_error = commit_error
        self.statements = []
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.executed = []

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, statement):
        self.statements.append(statement)
        return Rows(self.scalar_rows.pop(0) if self.scalar_rows else [])

    async def execute(self, statement):
        self.executed.append(statement)
        return Rows(self.scalar_rows.pop(0) if self.scalar_rows else [])

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if isinstance(value, ExerciseSubmission) and value.id is None:
                value.id = uuid.uuid4()

    async def commit(self):
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True
        now = datetime.now(timezone.utc)
        for value in self.added:
            if hasattr(value, "created_at") and value.created_at is None:
                value.created_at = now
            if hasattr(value, "updated_at") and value.updated_at is None:
                value.updated_at = now
            if hasattr(value, "submitted_at") and value.submitted_at is None:
                value.submitted_at = now

    async def refresh(self, _value):
        return None

    async def rollback(self):
        self.rolled_back = True


class ExerciseSubmissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.student_user = User(id=uuid.uuid4(), username="student", email="student@example.com", password_hash="hash")
        self.teacher_user = User(id=uuid.uuid4(), username="teacher", email="teacher@example.com", password_hash="hash")
        self.course = Course(id=uuid.uuid4(), department_id=uuid.uuid4(), code="CS101", name="Programming")
        self.lesson = Lesson(id=uuid.uuid4(), course_id=self.course.id, title="Lesson", content="Content", is_published=True)
        self.exercise = Exercise(id=uuid.uuid4(), lesson_id=self.lesson.id, title="Exercise", instructions="Solve it", exercise_type="WRITTEN", is_published=True)
        self.student = Student(id=uuid.uuid4(), user_id=self.student_user.id, institution_id=uuid.uuid4())
        self.teacher = Teacher(id=uuid.uuid4(), user_id=self.teacher_user.id, institution_id=self.student.institution_id)
        self.attempt = ExerciseSubmission(
            id=uuid.uuid4(),
            exercise_id=self.exercise.id,
            student_id=self.student.id,
            attempt_number=1,
            answer_text="My answer",
            submitted_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    async def test_student_submission_records_activity_and_notifies_assigned_teacher(self):
        session = ExerciseSession(
            [self.exercise, self.lesson, self.student],
            [[self.teacher_user.id]],
        )
        response = await create_exercise_submission(
            self.exercise.id,
            ExerciseSubmissionCreate(attempt_number=1, answer_text="  My answer  "),
            self.student_user,
            session,
        )
        self.assertEqual(response["answer_text"], "My answer")
        self.assertEqual(response["student_id"], str(self.student.id))
        self.assertTrue(session.committed)
        event = next(value for value in session.added if isinstance(value, Activity))
        self.assertEqual(event.event_type, "education.exercise.submitted")
        self.assertEqual(event.payload, {"attempt_number": 1})
        notification = next(value for value in session.added if isinstance(value, Notification))
        self.assertEqual(notification.recipient_id, self.teacher_user.id)
        self.assertNotIn("answer", str(notification.payload))
        authorization_sql = str(session.statements[2].compile())
        self.assertIn("students.institution_id = faculties.institution_id", authorization_sql)
        self.assertIn("institution_memberships.role", authorization_sql)
        self.assertIn("users.is_active", authorization_sql)

    async def test_submission_requires_published_exercise_and_course_enrollment(self):
        with self.assertRaises(HTTPException) as missing_error:
            await create_exercise_submission(
                self.exercise.id,
                ExerciseSubmissionCreate(attempt_number=1, answer_text="answer"),
                self.student_user,
                ExerciseSession([None]),
            )
        self.assertEqual(missing_error.exception.status_code, 404)

        unpublished_lesson = Lesson(id=self.lesson.id, course_id=self.course.id, title="Hidden", content="Content", is_published=False)
        with self.assertRaises(HTTPException) as hidden_error:
            await create_exercise_submission(
                self.exercise.id,
                ExerciseSubmissionCreate(attempt_number=1, answer_text="answer"),
                self.student_user,
                ExerciseSession([self.exercise, unpublished_lesson]),
            )
        self.assertEqual(hidden_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as enrollment_error:
            await create_exercise_submission(
                self.exercise.id,
                ExerciseSubmissionCreate(attempt_number=1, answer_text="answer"),
                self.student_user,
                ExerciseSession([self.exercise, self.lesson, None]),
            )
        self.assertEqual(enrollment_error.exception.status_code, 403)

    async def test_duplicate_attempt_rolls_back_database_and_activity(self):
        failure = IntegrityError("insert", {}, RuntimeError("duplicate attempt"))
        session = ExerciseSession(
            [self.exercise, self.lesson, self.student],
            [[]],
            commit_error=failure,
        )
        with self.assertRaises(HTTPException) as error:
            await create_exercise_submission(
                self.exercise.id,
                ExerciseSubmissionCreate(attempt_number=2, answer_text="retry"),
                self.student_user,
                session,
            )
        self.assertEqual(error.exception.status_code, 409)
        self.assertTrue(session.rolled_back)
        self.assertTrue(any(isinstance(value, Activity) for value in session.added))

    async def test_students_only_read_their_own_attempts_and_teachers_can_review(self):
        owner_session = ExerciseSession(
            [self.attempt, self.exercise, self.lesson, self.student.id, self.student]
        )
        own_response = await get_exercise_submission(self.attempt.id, self.student_user, owner_session)
        self.assertEqual(own_response["id"], str(self.attempt.id))
        self.assertIn("institution_memberships.role", str(owner_session.statements[4].compile()))
        self.assertIn("users.is_active", str(owner_session.statements[4].compile()))

        other_user = User(id=uuid.uuid4(), username="other", email="other@example.com", password_hash="hash")
        forbidden = ExerciseSession([self.attempt, self.exercise, self.lesson, None, None])
        with self.assertRaises(HTTPException) as access_error:
            await get_exercise_submission(self.attempt.id, other_user, forbidden)
        self.assertEqual(access_error.exception.status_code, 403)

        review_session = ExerciseSession(
            [self.attempt, self.exercise, self.lesson, self.teacher, self.student]
        )
        reviewed = await review_exercise_submission(
            self.attempt.id,
            ExerciseSubmissionReview(feedback="Good work"),
            self.teacher_user,
            review_session,
        )
        self.assertEqual(reviewed["feedback"], "Good work")
        self.assertEqual(reviewed["reviewer_id"], str(self.teacher_user.id))
        self.assertIsNotNone(reviewed["reviewed_at"])
        self.assertTrue(any(isinstance(value, Notification) for value in review_session.added))
        teacher_authorization_sql = str(review_session.statements[3].compile())
        self.assertIn("institution_memberships.role", teacher_authorization_sql)
        self.assertIn("users.is_active", teacher_authorization_sql)

    async def test_list_scope_and_teacher_access(self):
        own_session = ExerciseSession(
            [self.exercise, self.lesson, None, self.student],
            [[self.attempt]],
        )
        own = await list_exercise_submissions(self.exercise.id, self.student_user, own_session)
        self.assertEqual([value["id"] for value in own], [str(self.attempt.id)])
        student_authorization_sql = str(own_session.statements[3].compile())
        self.assertIn("institution_memberships.role", student_authorization_sql)
        self.assertIn("users.is_active", student_authorization_sql)
        self.assertIn("exercise_submissions.student_id =", str(own_session.statements[-1].compile()))

        teacher_session = ExerciseSession(
            [self.exercise, self.lesson, self.teacher],
            [[self.attempt]],
        )
        for_teacher = await list_exercise_submissions(self.exercise.id, self.teacher_user, teacher_session)
        self.assertEqual(len(for_teacher), 1)
        teacher_authorization_sql = str(teacher_session.statements[2].compile())
        self.assertIn("institution_memberships.role", teacher_authorization_sql)
        self.assertIn("users.is_active", teacher_authorization_sql)
        self.assertNotIn("exercise_submissions.student_id =", str(teacher_session.statements[-1].compile()))

    async def test_course_inbox_is_teacher_only_and_returns_student_names(self):
        reviewed_at = datetime.now(timezone.utc)
        self.attempt.reviewed_at = reviewed_at
        pending_attempt = ExerciseSubmission(
            id=uuid.uuid4(), exercise_id=self.exercise.id, student_id=self.student.id,
            attempt_number=2, answer_text="Pending", submitted_at=datetime.now(timezone.utc),
        )
        pending_row = (pending_attempt, self.lesson.id, self.lesson.title, self.exercise.title, "Student Name", "student")
        reviewed_row = (self.attempt, self.lesson.id, self.lesson.title, self.exercise.title, None, "student")
        session = ExerciseSession([self.teacher], [[pending_row, reviewed_row]])

        results = await list_course_exercise_submissions(self.course.id, self.teacher_user, session)
        self.assertEqual([item["student_name"] for item in results], ["Student Name", "student"])
        self.assertEqual([item["reviewed_at"] for item in results], [None, reviewed_at])
        query = str(session.executed[0].compile()).lower()
        self.assertIn("profiles.display_name", query)
        self.assertIn("institution_memberships.role", str(session.statements[0].compile()).lower())
        self.assertIn("nulls first", query)

        forbidden_session = ExerciseSession([None])
        with self.assertRaises(HTTPException) as error:
            await list_course_exercise_submissions(self.course.id, self.student_user, forbidden_session)
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(forbidden_session.executed, [])

    async def test_invalid_submission_input_and_unauthenticated_endpoint(self):
        with self.assertRaises(ValidationError):
            ExerciseSubmissionCreate(attempt_number=0, answer_text="answer")
        with self.assertRaises(ValidationError):
            ExerciseSubmissionCreate(attempt_number=1, answer_text="   ")

        app = FastAPI()
        app.include_router(router)

        async def override_session():
            yield ExerciseSession()

        app.dependency_overrides[get_postgres_session] = override_session
        with TestClient(app) as client:
            response = client.post(
                f"/education/exercises/{self.exercise.id}/submissions",
                json={"attempt_number": 1, "answer_text": "answer"},
            )
        app.dependency_overrides.clear()
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()