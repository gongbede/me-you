import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import Course, Department, Enrollment, Faculty, Institution, InstitutionMembership, Student, Teacher, User
from ..permissions import course_institution_id, require_student_membership_for_institution
from ..schemas import EnrollmentCreate, EnrollmentResponse, InstitutionMembershipRequestResponse, StudentCreate, StudentResponse, TeacherCreate, TeacherResponse
from ..security import get_current_postgres_user
from .institutions import create_membership_join_request, membership_request_response


router = APIRouter(prefix="/education", tags=["education"])


def parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} must be a UUID") from None


def student_response(value: Student) -> dict:
    return {"id": str(value.id), "user_id": str(value.user_id), "institution_id": str(value.institution_id), "created_at": value.created_at, "updated_at": value.updated_at}


def teacher_response(value: Teacher) -> dict:
    return {"id": str(value.id), "user_id": str(value.user_id), "institution_id": str(value.institution_id), "created_at": value.created_at, "updated_at": value.updated_at}


def enrollment_response(value: Enrollment) -> dict:
    return {"id": str(value.id), "student_id": str(value.student_id), "course_id": str(value.course_id), "created_at": value.created_at, "updated_at": value.updated_at}


@router.post("/students/me", response_model=InstitutionMembershipRequestResponse, status_code=status.HTTP_202_ACCEPTED, summary="Request student membership")
async def register_student(data: StudentCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session), request: Request = None):
    institution_id = parse_uuid(data.institution_id, "institution_id")
    value = await create_membership_join_request(
        institution_id, "STUDENT", current_user, database, request
    )
    return membership_request_response(value)


@router.get("/students/me", response_model=list[StudentResponse], summary="List current student records")
async def list_my_students(current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session), offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 100):
    values = list((await database.scalars(select(Student).where(Student.user_id == current_user.id).order_by(Student.created_at.asc(), Student.id.asc()).offset(offset).limit(limit))).all())
    return [student_response(value) for value in values]


@router.post("/teachers/me", response_model=InstitutionMembershipRequestResponse, status_code=status.HTTP_202_ACCEPTED, summary="Request teacher membership")
async def register_teacher(data: TeacherCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session), request: Request = None):
    institution_id = parse_uuid(data.institution_id, "institution_id")
    value = await create_membership_join_request(
        institution_id, "TEACHER", current_user, database, request
    )
    return membership_request_response(value)


@router.get("/teachers/me", response_model=list[TeacherResponse], summary="List current teacher records")
async def list_my_teachers(current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session), offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 100):
    values = list((await database.scalars(select(Teacher).where(Teacher.user_id == current_user.id).order_by(Teacher.created_at.asc(), Teacher.id.asc()).offset(offset).limit(limit))).all())
    return [teacher_response(value) for value in values]


@router.post("/enrollments", response_model=EnrollmentResponse, status_code=201, summary="Enroll in a course")
async def create_enrollment(data: EnrollmentCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    course_id = parse_uuid(data.course_id, "course_id")
    course = await database.scalar(select(Course).where(Course.id == course_id))
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    course_institution_uuid = await course_institution_id(course.id, database)
    student = await require_student_membership_for_institution(
        current_user.id,
        course_institution_uuid,
        database,
    )
    if student.institution_id != course_institution_uuid:
        raise HTTPException(status_code=403, detail="Student does not belong to the course institution")
    value = Enrollment(student_id=student.id, course_id=course.id, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    database.add(value)
    try:
        await database.commit()
        await database.refresh(value)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="Enrollment already exists") from None
    return enrollment_response(value)


@router.get("/enrollments", response_model=list[EnrollmentResponse], summary="List current enrollments")
async def list_my_enrollments(current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session), offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 100):
    values = list(
        (
            await database.scalars(
                select(Enrollment)
                .join(Student, Student.id == Enrollment.student_id)
                .join(Course, Course.id == Enrollment.course_id)
                .join(Department, Department.id == Course.department_id)
                .join(Faculty, Faculty.id == Department.faculty_id)
                .join(
                    InstitutionMembership,
                    InstitutionMembership.user_id == Student.user_id,
                )
                .join(User, User.id == Student.user_id)
                .where(
                    Student.user_id == current_user.id,
                    Student.institution_id == Faculty.institution_id,
                    InstitutionMembership.institution_id == Faculty.institution_id,
                    InstitutionMembership.role == "STUDENT",
                    User.is_active.is_(True),
                )
                .order_by(Enrollment.created_at.desc(), Enrollment.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return [enrollment_response(value) for value in values]


@router.get("/enrollments/{enrollment_id}", response_model=EnrollmentResponse, summary="Get an enrollment")
async def get_my_enrollment(enrollment_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(
        select(Enrollment)
        .join(Student, Student.id == Enrollment.student_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Department, Department.id == Course.department_id)
        .join(Faculty, Faculty.id == Department.faculty_id)
        .join(
            InstitutionMembership,
            InstitutionMembership.user_id == Student.user_id,
        )
        .join(User, User.id == Student.user_id)
        .where(
            Enrollment.id == enrollment_id,
            Student.user_id == current_user.id,
            Student.institution_id == Faculty.institution_id,
            InstitutionMembership.institution_id == Faculty.institution_id,
            InstitutionMembership.role == "STUDENT",
            User.is_active.is_(True),
        )
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return enrollment_response(value)
