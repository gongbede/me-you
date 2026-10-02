import uuid
import unittest
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.models import Activity, Course, Department, Faculty, Institution, InstitutionMembership, Student, Teacher
from app.routes.education import create_enrollment, register_student, register_teacher
from app.routes.institutions import create_course, create_department, create_faculty, create_institution
from app.schemas import CourseCreate, DepartmentCreate, EnrollmentCreate, FacultyCreate, InstitutionCreate, StudentCreate, TeacherCreate
from app.models import User


class EducationSession:
    def __init__(self, scalar_values=None, commit_error=None):
        self.scalar_values = list(scalar_values or [])
        self.added = []
        self.added_history = []
        self.committed = False
        self.commit_error = commit_error
        self.rolled_back = False

    async def scalar(self, _statement):
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, _statement):
        return Result([])

    def add(self, value):
        self.added.append(value)
        self.added_history.append(value)

    async def flush(self):
        for value in self.added:
            if hasattr(value, "id") and value.id is None:
                value.id = uuid.uuid4()

    async def commit(self):
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True
        now = datetime.now(timezone.utc)
        for value in self.added:
            if hasattr(value, "id") and value.id is None:
                value.id = uuid.uuid4()
            if hasattr(value, "created_at") and value.created_at is None:
                value.created_at = now
            if hasattr(value, "updated_at") and value.updated_at is None:
                value.updated_at = now

    async def refresh(self, _value):
        return None

    async def rollback(self):
        self.rolled_back = True
        self.added.clear()


class Result:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class EducationCoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = User(id=uuid.uuid4(), username="student", email="student@example.com", password_hash="hash")
        self.institution = Institution(id=uuid.uuid4(), name="Me&You University", institution_type="UNIVERSITY")
        self.faculty = Faculty(id=uuid.uuid4(), institution_id=self.institution.id, name="Science")
        self.department = Department(id=uuid.uuid4(), faculty_id=self.faculty.id, name="Computing")
        self.course = Course(id=uuid.uuid4(), department_id=self.department.id, code="CS101", name="Programming")
        self.student = Student(id=uuid.uuid4(), user_id=self.user.id, institution_id=self.institution.id)

    async def test_institution_hierarchy_and_invalid_parent(self):
        institution_session = EducationSession()
        result = await create_institution(InstitutionCreate(name="New School", institution_type="SCHOOL"), self.user, institution_session)
        self.assertEqual(result["name"], "New School")

        admin_membership = InstitutionMembership(id=uuid.uuid4(), user_id=self.user.id, institution_id=self.institution.id, role="ADMIN")
        faculty_result = await create_faculty(self.institution.id, FacultyCreate(name="Arts"), self.user, EducationSession([self.institution.id, admin_membership]))
        self.assertEqual(faculty_result["institution_id"], str(self.institution.id))

        with self.assertRaises(HTTPException) as error:
            await create_department(uuid.uuid4(), DepartmentCreate(name="Missing"), self.user, EducationSession())
        self.assertEqual(error.exception.status_code, 404)

        with self.assertRaises(ValidationError) as blank_error:
            InstitutionCreate(name="   ", institution_type="SCHOOL")
        self.assertIn("value must not be blank", str(blank_error.exception))

    async def test_course_creation_and_duplicate_error(self):
        admin_membership = InstitutionMembership(id=uuid.uuid4(), user_id=self.user.id, institution_id=self.institution.id, role="ADMIN")
        session = EducationSession([self.department, self.faculty, admin_membership])
        course_result = await create_course(self.department.id, CourseCreate(code="CS201", name="Databases"), self.user, session)
        self.assertEqual(course_result["code"], "CS201")
        activities = [value for value in session.added if isinstance(value, Activity)]
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0].event_type, "education.course.created")
        self.assertEqual(activities[0].actor_id, self.user.id)
        self.assertEqual(activities[0].target_type, "course")
        self.assertEqual(activities[0].target_id, uuid.UUID(course_result["id"]))
        self.assertIsNone(activities[0].payload)

    async def test_course_integrity_failure_rolls_back_activity(self):
        admin_membership = InstitutionMembership(id=uuid.uuid4(), user_id=self.user.id, institution_id=self.institution.id, role="ADMIN")
        failure = IntegrityError("insert", {}, RuntimeError("duplicate course"))
        session = EducationSession([self.department, self.faculty, admin_membership], commit_error=failure)

        with self.assertRaises(HTTPException) as error:
            await create_course(self.department.id, CourseCreate(code="CS201", name="Databases"), self.user, session)

        self.assertEqual(error.exception.status_code, 409)
        self.assertTrue(session.rolled_back)
        self.assertTrue(any(isinstance(value, Activity) for value in session.added_history))
        self.assertFalse(any(isinstance(value, Activity) for value in session.added))

    async def test_teacher_and_student_identity_comes_from_authenticated_user(self):
        teacher_result = await register_teacher(TeacherCreate(institution_id=str(self.institution.id)), self.user, EducationSession([self.institution.id]))
        self.assertEqual(teacher_result["user_id"], str(self.user.id))
        student_result = await register_student(StudentCreate(institution_id=str(self.institution.id)), self.user, EducationSession([self.institution.id]))
        self.assertEqual(student_result["user_id"], str(self.user.id))

    async def test_enrollment_requires_current_student(self):
        result = await create_enrollment(EnrollmentCreate(course_id=str(self.course.id)), self.user, EducationSession([self.course, self.institution.id, self.student]))
        self.assertEqual(result["student_id"], str(self.student.id))
        self.assertEqual(result["course_id"], str(self.course.id))

        with self.assertRaises(HTTPException) as error:
            await create_enrollment(EnrollmentCreate(course_id=str(uuid.uuid4())), self.user, EducationSession([None]))
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
