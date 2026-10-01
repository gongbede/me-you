import importlib
import os
import unittest
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import validate_jwt_secret
from app.models import ConversationMember, Course, Department, Faculty, Institution, Student, Teacher, User
from app.permissions import require_institution_admin, require_institution_membership
from app.routes.education import create_enrollment
from app.routes.education_learning import assign_teacher
from app.routes.institutions import (
    get_course,
    get_department,
    get_faculty,
    get_institution,
    list_courses,
    list_departments,
    list_faculties,
    list_institutions,
)
from app.routes.messages import mark_read


class HardeningSession:
    def __init__(self, scalar_values=None, scalars_values=None):
        self.scalar_values = list(scalar_values or [])
        self.scalars_values = list(scalars_values or [])

    async def scalar(self, _statement):
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, _statement):
        if not self.scalars_values:
            return type("Result", (), {"all": lambda self: []})()
        return type("Result", (), {"all": lambda self, values=None: values or self._values, "_values": self.scalars_values.pop(0)})()

    async def commit(self):
        return None

    async def refresh(self, _value):
        return None

    async def rollback(self):
        return None


class SecurityHardeningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = User(id=uuid.uuid4(), username="alice", email="alice@example.com", password_hash="hash")
        self.other = User(id=uuid.uuid4(), username="bob", email="bob@example.com", password_hash="hash")
        self.institution_a = Institution(id=uuid.uuid4(), name="Alpha", institution_type="UNIVERSITY")
        self.institution_b = Institution(id=uuid.uuid4(), name="Beta", institution_type="SCHOOL")
        self.faculty_a = Faculty(id=uuid.uuid4(), institution_id=self.institution_a.id, name="Science")
        self.department_a = Department(id=uuid.uuid4(), faculty_id=self.faculty_a.id, name="Computing")
        self.course_a = Course(id=uuid.uuid4(), department_id=self.department_a.id, code="CS101", name="Intro")
        self.faculty_b = Faculty(id=uuid.uuid4(), institution_id=self.institution_b.id, name="Arts")
        self.department_b = Department(id=uuid.uuid4(), faculty_id=self.faculty_b.id, name="Music")
        self.course_b = Course(id=uuid.uuid4(), department_id=self.department_b.id, code="MUS101", name="Music")
        self.student_a = Student(id=uuid.uuid4(), user_id=self.user.id, institution_id=self.institution_a.id)
        self.teacher_b = Teacher(id=uuid.uuid4(), user_id=self.other.id, institution_id=self.institution_b.id)

    async def test_cross_institution_enrollment_is_rejected(self):
        session = HardeningSession([self.course_b, self.institution_b.id, self.student_a])
        with self.assertRaises(HTTPException) as error:
            await create_enrollment(type("Data", (), {"course_id": str(self.course_b.id)})(), self.user, session)
        self.assertEqual(error.exception.status_code, 403)

    async def test_course_teacher_assignment_requires_same_institution(self):
        session = HardeningSession([self.institution_a.id, None, self.teacher_b])
        with self.assertRaises(HTTPException) as error:
            await assign_teacher(self.course_a.id, type("Data", (), {"teacher_id": str(self.teacher_b.id)})(), self.user, session)
        self.assertEqual(error.exception.status_code, 403)

    async def test_institution_admin_requires_matching_institution(self):
        with self.assertRaises(HTTPException):
            await require_institution_admin(self.other.id, self.institution_a.id, HardeningSession([None]))

    async def test_mark_read_uses_previous_timestamp(self):
        now = datetime.now(timezone.utc)
        membership = ConversationMember(conversation_id=uuid.uuid4(), user_id=self.user.id, last_read_at=now)
        session = HardeningSession([membership, 2])
        response = await mark_read(membership.conversation_id, self.user, session)
        self.assertEqual(response["unread_count"], 2)
        self.assertIsNotNone(response["last_read_at"])

    async def test_list_institutions_only_returns_user_memberships(self):
        session = HardeningSession(scalars_values=[[self.institution_a.id], [self.institution_a]])
        result = await list_institutions(self.user, session)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], str(self.institution_a.id))

    async def test_member_cannot_access_other_institution_private_data(self):
        session = HardeningSession([self.institution_b, None])
        with self.assertRaises(HTTPException) as error:
            await get_institution(self.institution_b.id, self.user, session)
        self.assertEqual(error.exception.status_code, 403)

        with self.assertRaises(HTTPException) as error:
            await get_faculty(self.faculty_b.id, self.user, HardeningSession([self.faculty_b, None]))
        self.assertEqual(error.exception.status_code, 403)

        with self.assertRaises(HTTPException) as error:
            await get_department(self.department_b.id, self.user, HardeningSession([self.department_b, self.faculty_b, None]))
        self.assertEqual(error.exception.status_code, 403)

        with self.assertRaises(HTTPException) as error:
            await get_course(self.course_b.id, self.user, HardeningSession([self.course_b, self.department_b, self.faculty_b, None]))
        self.assertEqual(error.exception.status_code, 403)

        with self.assertRaises(HTTPException) as error:
            await list_faculties(self.institution_b.id, self.user, HardeningSession([self.institution_b, None]))
        self.assertEqual(error.exception.status_code, 403)

        with self.assertRaises(HTTPException) as error:
            await list_departments(self.faculty_b.id, self.user, HardeningSession([self.faculty_b, None]))
        self.assertEqual(error.exception.status_code, 403)

        with self.assertRaises(HTTPException) as error:
            await list_courses(self.department_b.id, self.user, HardeningSession([self.department_b, self.faculty_b, None]))
        self.assertEqual(error.exception.status_code, 403)

    async def test_multiple_memberships_remain_scoped_by_institution(self):
        membership_a = type("Membership", (), {"id": uuid.uuid4(), "user_id": self.user.id, "institution_id": self.institution_a.id, "role": "ADMIN"})()
        session = HardeningSession([membership_a, None, None])
        admin_membership = await require_institution_admin(self.user.id, self.institution_a.id, session)
        self.assertEqual(admin_membership.role, "ADMIN")
        with self.assertRaises(HTTPException):
            await require_institution_admin(self.user.id, self.institution_b.id, session)
        with self.assertRaises(HTTPException):
            await require_institution_membership(self.user.id, uuid.uuid4(), session)

    def test_production_secret_validation_requires_real_secret(self):
        module = importlib.import_module("app.config")
        old_env = os.environ.get("ME_YOU_ENV")
        old_secret = os.environ.get("ME_YOU_JWT_SECRET_KEY")
        try:
            os.environ["ME_YOU_ENV"] = "production"
            os.environ["ME_YOU_JWT_SECRET_KEY"] = "development-only-me-you-jwt-secret"
            with self.assertRaises(ValueError):
                validate_jwt_secret(environment="production", secret="development-only-me-you-jwt-secret")
        finally:
            if old_env is None:
                os.environ.pop("ME_YOU_ENV", None)
            else:
                os.environ["ME_YOU_ENV"] = old_env
            if old_secret is None:
                os.environ.pop("ME_YOU_JWT_SECRET_KEY", None)
            else:
                os.environ["ME_YOU_JWT_SECRET_KEY"] = old_secret
            importlib.reload(module)


if __name__ == "__main__":
    unittest.main()
