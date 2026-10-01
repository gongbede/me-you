import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Course,
    CourseTeacher,
    Department,
    Faculty,
    InstitutionMembership,
    Student,
    Teacher,
)

ADMIN_ROLE = "ADMIN"
TEACHER_ROLE = "TEACHER"
STUDENT_ROLE = "STUDENT"


async def require_institution_membership(user_id: uuid.UUID, institution_id: uuid.UUID, database: AsyncSession) -> InstitutionMembership:
    membership = await database.scalar(
        select(InstitutionMembership).where(
            InstitutionMembership.user_id == user_id,
            InstitutionMembership.institution_id == institution_id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Institution membership required",
        )
    return membership


async def require_institution_admin(user_id: uuid.UUID, institution_id: uuid.UUID, database: AsyncSession) -> InstitutionMembership:
    membership = await database.scalar(
        select(InstitutionMembership).where(
            InstitutionMembership.user_id == user_id,
            InstitutionMembership.institution_id == institution_id,
            InstitutionMembership.role == ADMIN_ROLE,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Institution administrator access required",
        )
    return membership


async def require_course_teacher(course_id: uuid.UUID, user_id: uuid.UUID, database: AsyncSession) -> Teacher:
    teacher = await database.scalar(
        select(Teacher)
        .join(CourseTeacher, CourseTeacher.teacher_id == Teacher.id)
        .where(CourseTeacher.course_id == course_id, Teacher.user_id == user_id)
    )
    if teacher is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assigned teacher access required",
        )
    return teacher


async def require_enrolled_student(course_id: uuid.UUID, user_id: uuid.UUID, database: AsyncSession) -> Student:
    student = await database.scalar(
        select(Student)
        .join(Course, Course.department_id == Department.id)
        .join(Faculty, Faculty.id == Department.faculty_id)
        .join(Department, Department.id == Course.department_id)
        .where(Course.id == course_id, Student.user_id == user_id, Student.institution_id == Faculty.institution_id)
    )
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Course enrollment required",
        )
    return student


async def course_institution_id(course_id: uuid.UUID, database: AsyncSession) -> uuid.UUID:
    value = await database.scalar(
        select(Faculty.institution_id)
        .join(Department, Department.faculty_id == Faculty.id)
        .join(Course, Course.department_id == Department.id)
        .where(Course.id == course_id)
    )
    if value is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return value


async def same_institution_or_403(left_id: uuid.UUID, right_id: uuid.UUID, label: str = "resource") -> None:
    if left_id != right_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{label} does not belong to the same institution",
        )


async def require_student_membership_for_institution(user_id: uuid.UUID, institution_id: uuid.UUID, database: AsyncSession) -> Student:
    student = await database.scalar(
        select(Student).where(Student.user_id == user_id, Student.institution_id == institution_id)
    )
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student membership not found",
        )
    return student


async def list_user_institution_ids(user_id: uuid.UUID, database: AsyncSession) -> set[uuid.UUID]:
    institution_ids = await database.scalars(
        select(InstitutionMembership.institution_id).where(InstitutionMembership.user_id == user_id)
    )
    return set(institution_ids.all())
