import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from .models import (
    Course,
    CourseTeacher,
    Conversation,
    ConversationMember,
    Department,
    Enrollment,
    Faculty,
    InstitutionMembership,
    Student,
    Teacher,
    User,
)

ADMIN_ROLE = "ADMIN"
TEACHER_ROLE = "TEACHER"
STUDENT_ROLE = "STUDENT"


def require_platform_admin(user: User) -> User:
    if getattr(user, "is_platform_admin", False) is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access required",
        )
    return user


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


async def count_active_institution_admins(
    institution_id: uuid.UUID,
    database: AsyncSession,
) -> tuple[int, set[uuid.UUID]]:
    memberships = list(
        (
            await database.scalars(
                select(InstitutionMembership)
                .join(User, User.id == InstitutionMembership.user_id)
                .options(contains_eager(InstitutionMembership.user))
                .where(
                    InstitutionMembership.institution_id == institution_id,
                    InstitutionMembership.role == ADMIN_ROLE,
                )
                .order_by(InstitutionMembership.id)
                .with_for_update(of=InstitutionMembership)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    active_admin_user_ids = {
        membership.user_id
        for membership in memberships
        if membership.user.is_active
    }
    return len(active_admin_user_ids), active_admin_user_ids


async def ensure_account_can_be_deactivated(
    user_id: uuid.UUID,
    database: AsyncSession,
    *,
    is_platform_admin: bool,
) -> None:
    institution_ids = list(
        (
            await database.scalars(
                select(InstitutionMembership.institution_id).where(
                    InstitutionMembership.user_id == user_id,
                    InstitutionMembership.role == ADMIN_ROLE,
                ).order_by(InstitutionMembership.institution_id)
            )
        ).all()
    )
    for institution_id in institution_ids:
        active_admin_count, active_admin_user_ids = await count_active_institution_admins(
            institution_id,
            database,
        )
        if user_id in active_admin_user_ids and active_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transfer institution administration before deactivating this account",
            )

    owned_group_ids = list(
        (
            await database.scalars(
                select(Conversation.id)
                .where(
                    Conversation.created_by_id == user_id,
                    Conversation.type == "GROUP",
                )
                .order_by(Conversation.id)
                .with_for_update()
            )
        ).all()
    )
    for conversation_id in owned_group_ids:
        active_member_id = await database.scalar(
            select(ConversationMember.user_id)
            .join(User, User.id == ConversationMember.user_id)
            .where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id != user_id,
                User.is_active.is_(True),
            )
            .order_by(ConversationMember.joined_at, ConversationMember.user_id)
            .limit(1)
        )
        if active_member_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transfer group ownership before deactivating this account",
            )

    if is_platform_admin:
        active_platform_admin_ids = list(
            (
                await database.scalars(
                    select(User.id)
                    .where(User.is_platform_admin.is_(True), User.is_active.is_(True))
                    .order_by(User.id)
                    .with_for_update()
                )
            ).all()
        )
        if len(active_platform_admin_ids) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot deactivate the final platform administrator",
            )


async def require_course_teacher(course_id: uuid.UUID, user_id: uuid.UUID, database: AsyncSession) -> Teacher:
    teacher = await database.scalar(
        select(Teacher)
        .join(CourseTeacher, CourseTeacher.teacher_id == Teacher.id)
        .join(InstitutionMembership, InstitutionMembership.user_id == Teacher.user_id)
        .join(User, User.id == Teacher.user_id)
        .join(Course, Course.id == CourseTeacher.course_id)
        .join(Department, Department.id == Course.department_id)
        .join(Faculty, Faculty.id == Department.faculty_id)
        .where(
            CourseTeacher.course_id == course_id,
            Teacher.user_id == user_id,
            Teacher.institution_id == Faculty.institution_id,
            InstitutionMembership.institution_id == Teacher.institution_id,
            InstitutionMembership.role == TEACHER_ROLE,
            User.is_active.is_(True),
        )
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
        .join(Enrollment, Enrollment.student_id == Student.id)
        .join(InstitutionMembership, InstitutionMembership.user_id == Student.user_id)
        .join(User, User.id == Student.user_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Department, Department.id == Course.department_id)
        .join(Faculty, Faculty.id == Department.faculty_id)
        .where(
            Enrollment.course_id == course_id,
            Student.user_id == user_id,
            Student.institution_id == Faculty.institution_id,
            InstitutionMembership.institution_id == Student.institution_id,
            InstitutionMembership.role == STUDENT_ROLE,
            User.is_active.is_(True),
        )
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
        select(Student)
        .join(InstitutionMembership, InstitutionMembership.user_id == Student.user_id)
        .join(User, User.id == Student.user_id)
        .where(
            Student.user_id == user_id,
            Student.institution_id == institution_id,
            InstitutionMembership.institution_id == institution_id,
            InstitutionMembership.role == STUDENT_ROLE,
            User.is_active.is_(True),
        )
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
