import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from app.models import ClassSession, Course, Student, Teacher, User
from app.routes.classrooms import create_class_session, join_class_session, session_access
from app.schemas import ClassSessionCreate


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class ClassroomSession:
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
        return Rows(self.scalar_rows.pop(0) if self.scalar_rows else [])

    def add(self, value):
        self.added.append(value)

    def add_all(self, values):
        self.added.extend(values)

    async def flush(self):
        for value in self.added:
            if isinstance(value, ClassSession) and value.id is None:
                value.id = uuid.uuid4()

    async def commit(self):
        self.committed = True

    async def refresh(self, _value):
        return None


class ClassroomTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.teacher_user = User(id=uuid.uuid4(), username="teacher", email="teacher@example.test", password_hash="x")
        self.student_user = User(id=uuid.uuid4(), username="student", email="student@example.test", password_hash="x")
        self.course = Course(id=uuid.uuid4(), department_id=uuid.uuid4(), code="CLS101", name="Classroom")
        self.teacher = Teacher(id=uuid.uuid4(), user_id=self.teacher_user.id, institution_id=uuid.uuid4())
        self.student = Student(id=uuid.uuid4(), user_id=self.student_user.id, institution_id=self.teacher.institution_id)

    def test_session_schema_requires_timezone_and_valid_window(self):
        starts_at = datetime.now(timezone.utc)
        with self.assertRaises(ValidationError):
            ClassSessionCreate(title="Live session", starts_at=starts_at, ends_at=starts_at)
        with self.assertRaises(ValidationError):
            ClassSessionCreate(title="Live session", starts_at=starts_at.replace(tzinfo=None), ends_at=starts_at + timedelta(hours=1))

    async def test_only_assigned_teacher_can_schedule_and_attendance_is_seeded(self):
        starts_at = datetime.now(timezone.utc) + timedelta(hours=1)
        data = ClassSessionCreate(title="Study together", starts_at=starts_at, ends_at=starts_at + timedelta(hours=1))
        session = ClassroomSession([self.teacher], [[self.student.user_id]])
        response = await create_class_session(uuid.uuid4(), data, self.teacher_user, session)
        self.assertEqual(response["status"], "SCHEDULED")
        self.assertTrue(session.committed)
        self.assertEqual(len(session.added), 2)
        self.assertEqual(session.added[1].status, "ABSENT")

        with self.assertRaises(HTTPException) as error:
            await create_class_session(uuid.uuid4(), data, self.student_user, ClassroomSession([None]))
        self.assertEqual(error.exception.status_code, 403)

    async def test_session_access_requires_teacher_assignment_or_enrollment(self):
        value = ClassSession(
            id=uuid.uuid4(), course_id=self.course.id, created_by_id=self.teacher_user.id,
            title="Live", starts_at=datetime.now(timezone.utc), ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        teacher_access = ClassroomSession([self.course.id, self.teacher])
        self.assertTrue(await session_access(value, self.teacher_user, teacher_access))
        student_access = ClassroomSession([self.course.id, None, self.student])
        self.assertFalse(await session_access(value, self.student_user, student_access))
        with self.assertRaises(HTTPException) as error:
            await session_access(value, User(id=uuid.uuid4()), ClassroomSession([self.course.id, None, None]))
        self.assertEqual(error.exception.status_code, 403)

    async def test_join_requires_a_live_session_and_enrolled_identity(self):
        scheduled = ClassSession(
            id=uuid.uuid4(), course_id=self.course.id, created_by_id=self.teacher_user.id,
            title="Scheduled", starts_at=datetime.now(timezone.utc), ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
            status="SCHEDULED",
        )
        with self.assertRaises(HTTPException) as error:
            await join_class_session(scheduled.id, self.student_user, ClassroomSession([scheduled]))
        self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()