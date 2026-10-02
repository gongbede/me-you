import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity import record_activity
from ..database import get_postgres_session
from ..models import (
    Assessment,
    AssessmentResult,
    AssessmentSubmission,
    Course,
    CourseTeacher,
    Department,
    Enrollment,
    Exercise,
    Faculty,
    Institution,
    InstitutionMembership,
    Lesson,
    LessonProgress,
    Student,
    Teacher,
    User,
)
from ..permissions import list_user_institution_ids, require_institution_admin, require_institution_membership
from ..schemas import (
    CourseCreate,
    CourseResponse,
    DepartmentCreate,
    DepartmentResponse,
    FacultyCreate,
    FacultyResponse,
    InstitutionCreate,
    InstitutionMembershipCreate,
    InstitutionMembershipResponse,
    InstitutionMembershipUpdate,
    InstitutionResponse,
    StudentResponse,
    TeacherResponse,
)
from ..security import get_current_postgres_user


router = APIRouter(prefix="/institutions", tags=["education"])


def institution_response(value: Institution) -> dict:
    return {"id": str(value.id), "name": value.name, "description": value.description, "institution_type": value.institution_type, "website": value.website, "location": value.location, "created_at": value.created_at, "updated_at": value.updated_at}


def faculty_response(value: Faculty) -> dict:
    return {"id": str(value.id), "institution_id": str(value.institution_id), "name": value.name, "description": value.description, "created_at": value.created_at, "updated_at": value.updated_at}


def department_response(value: Department) -> dict:
    return {"id": str(value.id), "faculty_id": str(value.faculty_id), "name": value.name, "description": value.description, "created_at": value.created_at, "updated_at": value.updated_at}


def course_response(value: Course) -> dict:
    return {"id": str(value.id), "department_id": str(value.department_id), "code": value.code, "name": value.name, "description": value.description, "created_at": value.created_at, "updated_at": value.updated_at}


def parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} must be a UUID") from None


VALID_MEMBER_ROLES = {"ADMIN", "TEACHER", "STUDENT"}


def normalize_member_role(data: object) -> str:
    if isinstance(data, dict):
        role = data.get("role")
    else:
        role = getattr(data, "role", None)
    if role not in VALID_MEMBER_ROLES:
        raise HTTPException(status_code=422, detail="role must be one of ADMIN, TEACHER, STUDENT")
    return role


def membership_response(value: InstitutionMembership) -> dict:
    return {
        "id": str(value.id),
        "user_id": str(value.user_id),
        "institution_id": str(value.institution_id),
        "role": getattr(value, "role", None),
        "created_at": getattr(value, "created_at", None),
        "updated_at": getattr(value, "updated_at", None),
    }


async def list_members(institution_id: uuid.UUID, current_user: User, database: AsyncSession):
    await require_institution_admin(current_user.id, institution_id, database)
    values = list((await database.scalars(select(InstitutionMembership).where(InstitutionMembership.institution_id == institution_id).order_by(InstitutionMembership.user_id.asc()))).all())
    return [membership_response(value) for value in values]


async def get_member(institution_id: uuid.UUID, membership_id: uuid.UUID, current_user: User, database: AsyncSession):
    await require_institution_admin(current_user.id, institution_id, database)
    value = await database.scalar(select(InstitutionMembership).where(InstitutionMembership.id == membership_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    if value.institution_id != institution_id:
        raise HTTPException(status_code=403, detail="Membership does not belong to this institution")
    return membership_response(value)


async def add_member(institution_id: uuid.UUID, target_user_id: uuid.UUID | str, role: str, current_user: User, database: AsyncSession):
    await require_institution_admin(current_user.id, institution_id, database)
    user_id = parse_uuid(str(target_user_id), "user_id")
    target_user = await database.scalar(select(User).where(User.id == user_id))
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if await database.scalar(select(InstitutionMembership.id).where(InstitutionMembership.user_id == user_id, InstitutionMembership.institution_id == institution_id)) is not None:
        raise HTTPException(status_code=409, detail="Membership already exists for this institution")
    if role not in VALID_MEMBER_ROLES:
        raise HTTPException(status_code=422, detail="role must be one of ADMIN, TEACHER, STUDENT")
    value = InstitutionMembership(user_id=user_id, institution_id=institution_id, role=role, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    database.add(value)
    try:
        await database.flush()
        await record_activity(
            database,
            event_type="institution.membership.added",
            actor_id=current_user.id,
            target_type="institution_membership",
            target_id=value.id,
            metadata={"role": role},
        )
        await database.commit()
        await database.refresh(value)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="Membership already exists") from None
    return membership_response(value)


async def _lock_institution_admin_rows(database: AsyncSession, institution_id: uuid.UUID):
    statement = select(InstitutionMembership).where(
        InstitutionMembership.institution_id == institution_id,
        InstitutionMembership.role == "ADMIN",
    )
    dialect = getattr(getattr(getattr(database, "bind", None), "dialect", None), "name", None)
    if dialect == "postgresql":
        statement = statement.with_for_update()
    return list((await database.scalars(statement)).all())


async def _guard_final_admin_mutation(database: AsyncSession, institution_id: uuid.UUID, membership: InstitutionMembership, *, action: str) -> None:
    if membership is None or membership.role != "ADMIN":
        return
    admin_rows = await _lock_institution_admin_rows(database, institution_id)
    admin_count = len(admin_rows)
    if admin_count <= 1 and any(row.id == membership.id for row in admin_rows):
        raise HTTPException(status_code=409, detail=f"Final administrator cannot be {action}")


async def _run_membership_mutation(database: AsyncSession, mutate, *, integrity_detail: str | None = None):
    in_transaction = getattr(database, "in_transaction", None)
    has_active_transaction = callable(in_transaction) and in_transaction()
    has_begin = callable(getattr(database, "begin", None))

    try:
        if has_active_transaction:
            result = await mutate()
            await database.commit()
            return result
        if has_begin:
            async with database.begin():
                return await mutate()
        result = await mutate()
        if hasattr(database, "commit"):
            await database.commit()
        return result
    except IntegrityError:
        if hasattr(database, "rollback"):
            await database.rollback()
        if integrity_detail is not None:
            raise HTTPException(status_code=409, detail=integrity_detail) from None
        raise
    except BaseException:
        if (has_active_transaction or not has_begin) and hasattr(database, "rollback"):
            await database.rollback()
        raise


async def update_member_role(institution_id: uuid.UUID, membership_id: uuid.UUID, data: object, current_user: User, database: AsyncSession):
    async def mutate() -> dict:
        await require_institution_admin(current_user.id, institution_id, database)
        role = normalize_member_role(data)
        value = await database.scalar(select(InstitutionMembership).where(InstitutionMembership.id == membership_id))
        if value is None:
            raise HTTPException(status_code=404, detail="Membership not found")
        if value.institution_id != institution_id:
            raise HTTPException(status_code=403, detail="Membership does not belong to this institution")
        previous_role = value.role
        if previous_role == "ADMIN" and role != "ADMIN":
            await _guard_final_admin_mutation(database, institution_id, value, action="demoted")
        value.role = role
        value.updated_at = datetime.now(timezone.utc)
        if previous_role != role:
            await record_activity(
                database,
                event_type="institution.membership.role_changed",
                actor_id=current_user.id,
                target_type="institution_membership",
                target_id=value.id,
                metadata={"previous_role": previous_role, "new_role": role},
            )
        await database.refresh(value)
        return membership_response(value)

    return await _run_membership_mutation(
        database,
        mutate,
        integrity_detail="Role update conflicts with existing constraints",
    )


async def remove_member(institution_id: uuid.UUID, membership_id: uuid.UUID, current_user: User, database: AsyncSession):
    async def mutate() -> None:
        await require_institution_admin(current_user.id, institution_id, database)
        value = await database.scalar(select(InstitutionMembership).where(InstitutionMembership.id == membership_id))
        if value is None:
            raise HTTPException(status_code=404, detail="Membership not found")
        if value.institution_id != institution_id:
            raise HTTPException(status_code=403, detail="Membership does not belong to this institution")
        if value.role == "ADMIN":
            await _guard_final_admin_mutation(database, institution_id, value, action="removed")
        await record_activity(
            database,
            event_type="institution.membership.removed",
            actor_id=current_user.id,
            target_type="institution_membership",
            target_id=value.id,
            metadata={"role": value.role},
        )
        await database.delete(value)

    await _run_membership_mutation(database, mutate)
    return None


async def list_institution_teachers(institution_id: uuid.UUID, current_user: User, database: AsyncSession):
    await require_institution_admin(current_user.id, institution_id, database)
    values = list((await database.scalars(select(Teacher).where(Teacher.institution_id == institution_id).order_by(Teacher.created_at.asc()))).all())
    return [{"id": str(value.id), "user_id": str(value.user_id), "institution_id": str(value.institution_id), "created_at": value.created_at, "updated_at": value.updated_at} for value in values]


async def get_institution_teacher(institution_id: uuid.UUID, teacher_id: uuid.UUID, current_user: User, database: AsyncSession):
    await require_institution_admin(current_user.id, institution_id, database)
    value = await database.scalar(select(Teacher).where(Teacher.id == teacher_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    if value.institution_id != institution_id:
        raise HTTPException(status_code=403, detail="Teacher does not belong to this institution")
    return {"id": str(value.id), "user_id": str(value.user_id), "institution_id": str(value.institution_id), "created_at": value.created_at, "updated_at": value.updated_at}


async def list_institution_students(institution_id: uuid.UUID, current_user: User, database: AsyncSession):
    await require_institution_admin(current_user.id, institution_id, database)
    values = list((await database.scalars(select(Student).where(Student.institution_id == institution_id).order_by(Student.created_at.asc()))).all())
    return [{"id": str(value.id), "user_id": str(value.user_id), "institution_id": str(value.institution_id), "created_at": value.created_at, "updated_at": value.updated_at} for value in values]


async def get_institution_student(institution_id: uuid.UUID, student_id: uuid.UUID, current_user: User, database: AsyncSession):
    await require_institution_admin(current_user.id, institution_id, database)
    value = await database.scalar(select(Student).where(Student.id == student_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if value.institution_id != institution_id:
        raise HTTPException(status_code=403, detail="Student does not belong to this institution")
    return {"id": str(value.id), "user_id": str(value.user_id), "institution_id": str(value.institution_id), "created_at": value.created_at, "updated_at": value.updated_at}


@router.post("", response_model=InstitutionResponse, status_code=201, summary="Create an institution")
async def create_institution(data: InstitutionCreate, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    institution = Institution(**data.model_dump(), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    database.add(institution)
    await database.flush()
    membership = InstitutionMembership(user_id=current_user.id, institution_id=institution.id, role="ADMIN", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    database.add(membership)
    await database.commit()
    await database.refresh(institution)
    return institution_response(institution)


@router.get("", response_model=list[InstitutionResponse], summary="List institutions")
async def list_institutions(current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    institution_ids = await list_user_institution_ids(current_user.id, database)
    if not institution_ids:
        return []
    values = list((await database.scalars(select(Institution).where(Institution.id.in_(sorted(institution_ids))).order_by(Institution.name.asc()))).all())
    return [institution_response(value) for value in values]


@router.get("/{institution_id}", response_model=InstitutionResponse, summary="Get an institution")
async def get_institution(institution_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Institution).where(Institution.id == institution_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    await require_institution_membership(current_user.id, institution_id, database)
    return institution_response(value)


@router.patch("/{institution_id}", response_model=InstitutionResponse, summary="Update an institution")
async def update_institution(institution_id: uuid.UUID, data: InstitutionCreate, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Institution).where(Institution.id == institution_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    await require_institution_admin(current_user.id, institution_id, database)
    for field, item in data.model_dump(exclude_unset=True).items():
        setattr(value, field, item)
    value.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(value)
    return institution_response(value)


@router.delete("/{institution_id}", status_code=204, summary="Delete an institution")
async def delete_institution(institution_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Institution).where(Institution.id == institution_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    await require_institution_admin(current_user.id, institution_id, database)
    if await database.scalar(select(Faculty.id).where(Faculty.institution_id == institution_id)) is not None:
        raise HTTPException(status_code=409, detail="Institution still has faculty records")
    if await database.scalar(select(Student.id).where(Student.institution_id == institution_id)) is not None:
        raise HTTPException(status_code=409, detail="Institution still has student records")
    if await database.scalar(select(Teacher.id).where(Teacher.institution_id == institution_id)) is not None:
        raise HTTPException(status_code=409, detail="Institution still has teacher records")
    if await database.scalar(select(InstitutionMembership.id).where(InstitutionMembership.institution_id == institution_id)) is not None:
        raise HTTPException(status_code=409, detail="Institution still has member records")
    await database.delete(value)
    await database.commit()


@router.get("/{institution_id}/members", response_model=list[InstitutionMembershipResponse], summary="List institution members")
async def list_members_route(institution_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    return await list_members(institution_id, current_user, database)


@router.get("/{institution_id}/members/{membership_id}", response_model=InstitutionMembershipResponse, summary="Get institution membership")
async def get_member_route(institution_id: uuid.UUID, membership_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    return await get_member(institution_id, membership_id, current_user, database)


@router.post("/{institution_id}/members", response_model=InstitutionMembershipResponse, status_code=201, summary="Add an institution member")
async def add_member_route(institution_id: uuid.UUID, data: InstitutionMembershipCreate, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    return await add_member(institution_id, data.user_id, data.role, current_user, database)


@router.patch("/{institution_id}/members/{membership_id}", response_model=InstitutionMembershipResponse, summary="Update an institution member role")
async def update_member_role_route(institution_id: uuid.UUID, membership_id: uuid.UUID, data: InstitutionMembershipUpdate, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    return await update_member_role(institution_id, membership_id, data, current_user, database)


@router.delete("/{institution_id}/members/{membership_id}", status_code=204, summary="Remove an institution member")
async def remove_member_route(institution_id: uuid.UUID, membership_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await remove_member(institution_id, membership_id, current_user, database)


@router.get("/{institution_id}/teachers", response_model=list[TeacherResponse], summary="List institution teachers")
async def list_institution_teachers_route(institution_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    values = await list_institution_teachers(institution_id, current_user, database)
    return values


@router.get("/teachers/{teacher_id}", response_model=TeacherResponse, summary="Get a teacher record")
async def get_institution_teacher_route(teacher_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Teacher).where(Teacher.id == teacher_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    await require_institution_admin(current_user.id, value.institution_id, database)
    return {"id": str(value.id), "user_id": str(value.user_id), "institution_id": str(value.institution_id), "created_at": value.created_at, "updated_at": value.updated_at}


@router.get("/{institution_id}/students", response_model=list[StudentResponse], summary="List institution students")
async def list_institution_students_route(institution_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    return await list_institution_students(institution_id, current_user, database)


@router.get("/students/{student_id}", response_model=StudentResponse, summary="Get a student record")
async def get_institution_student_route(student_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Student).where(Student.id == student_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Student not found")
    await require_institution_admin(current_user.id, value.institution_id, database)
    return {"id": str(value.id), "user_id": str(value.user_id), "institution_id": str(value.institution_id), "created_at": value.created_at, "updated_at": value.updated_at}


@router.post("/{institution_id}/faculties", response_model=FacultyResponse, status_code=201, summary="Create a faculty")
async def create_faculty(institution_id: uuid.UUID, data: FacultyCreate, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    if await database.scalar(select(Institution.id).where(Institution.id == institution_id)) is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    await require_institution_admin(current_user.id, institution_id, database)
    value = Faculty(institution_id=institution_id, **data.model_dump())
    database.add(value)
    try:
        await database.commit()
        await database.refresh(value)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="Faculty already exists in this institution") from None
    return faculty_response(value)


@router.get("/{institution_id}/faculties", response_model=list[FacultyResponse], summary="List institution faculties")
async def list_faculties(institution_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    if await database.scalar(select(Institution.id).where(Institution.id == institution_id)) is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    await require_institution_membership(current_user.id, institution_id, database)
    values = list((await database.scalars(select(Faculty).where(Faculty.institution_id == institution_id).order_by(Faculty.name.asc()))).all())
    return [faculty_response(value) for value in values]


@router.get("/faculties/{faculty_id}", response_model=FacultyResponse, summary="Get a faculty")
async def get_faculty(faculty_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Faculty).where(Faculty.id == faculty_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_membership(current_user.id, value.institution_id, database)
    return faculty_response(value)


@router.patch("/faculties/{faculty_id}", response_model=FacultyResponse, summary="Update a faculty")
async def update_faculty(faculty_id: uuid.UUID, data: FacultyCreate, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Faculty).where(Faculty.id == faculty_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_admin(current_user.id, value.institution_id, database)
    for field, item in data.model_dump(exclude_unset=True).items():
        setattr(value, field, item)
    value.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(value)
    return faculty_response(value)


@router.delete("/faculties/{faculty_id}", status_code=204, summary="Delete a faculty")
async def delete_faculty(faculty_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Faculty).where(Faculty.id == faculty_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_admin(current_user.id, value.institution_id, database)
    if await database.scalar(select(Department.id).where(Department.faculty_id == faculty_id)) is not None:
        raise HTTPException(status_code=409, detail="Faculty still has department records")
    if await database.scalar(select(Course.id).join(Department, Department.id == Course.department_id).where(Department.faculty_id == faculty_id)) is not None:
        raise HTTPException(status_code=409, detail="Faculty still has course records")
    await database.delete(value)
    await database.commit()


@router.post("/faculties/{faculty_id}/departments", response_model=DepartmentResponse, status_code=201, summary="Create a department")
async def create_department(faculty_id: uuid.UUID, data: DepartmentCreate, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    faculty = await database.scalar(select(Faculty).where(Faculty.id == faculty_id))
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_admin(current_user.id, faculty.institution_id, database)
    value = Department(faculty_id=faculty_id, **data.model_dump())
    database.add(value)
    try:
        await database.commit()
        await database.refresh(value)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="Department already exists in this faculty") from None
    return department_response(value)


@router.get("/departments/{department_id}", response_model=DepartmentResponse, summary="Get a department")
async def get_department(department_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Department).where(Department.id == department_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Department not found")
    faculty = await database.scalar(select(Faculty).where(Faculty.id == value.faculty_id))
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_membership(current_user.id, faculty.institution_id, database)
    return department_response(value)


@router.patch("/departments/{department_id}", response_model=DepartmentResponse, summary="Update a department")
async def update_department(department_id: uuid.UUID, data: DepartmentCreate, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Department).where(Department.id == department_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Department not found")
    faculty = await database.scalar(select(Faculty).where(Faculty.id == value.faculty_id))
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_admin(current_user.id, faculty.institution_id, database)
    for field, item in data.model_dump(exclude_unset=True).items():
        setattr(value, field, item)
    value.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(value)
    return department_response(value)


@router.delete("/departments/{department_id}", status_code=204, summary="Delete a department")
async def delete_department(department_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Department).where(Department.id == department_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Department not found")
    faculty = await database.scalar(select(Faculty).where(Faculty.id == value.faculty_id))
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_admin(current_user.id, faculty.institution_id, database)
    if await database.scalar(select(Course.id).where(Course.department_id == department_id)) is not None:
        raise HTTPException(status_code=409, detail="Department still has course records")
    await database.delete(value)
    await database.commit()


@router.get("/faculties/{faculty_id}/departments", response_model=list[DepartmentResponse], summary="List faculty departments")
async def list_departments(faculty_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    faculty = await database.scalar(select(Faculty).where(Faculty.id == faculty_id))
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_membership(current_user.id, faculty.institution_id, database)
    values = list((await database.scalars(select(Department).where(Department.faculty_id == faculty_id).order_by(Department.name.asc()))).all())
    return [department_response(value) for value in values]


@router.post("/departments/{department_id}/courses", response_model=CourseResponse, status_code=201, summary="Create a course")
async def create_course(department_id: uuid.UUID, data: CourseCreate, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    department = await database.scalar(select(Department).where(Department.id == department_id))
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    faculty = await database.scalar(select(Faculty).where(Faculty.id == department.faculty_id))
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_admin(current_user.id, faculty.institution_id, database)
    value = Course(department_id=department_id, **data.model_dump())
    database.add(value)
    try:
        await database.flush()
        await record_activity(
            database,
            event_type="education.course.created",
            actor_id=current_user.id,
            target_type="course",
            target_id=value.id,
        )
        await database.commit()
        await database.refresh(value)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="Course code already exists in this department") from None
    return course_response(value)


@router.get("/departments/{department_id}/courses", response_model=list[CourseResponse], summary="List department courses")
async def list_courses(department_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    department = await database.scalar(select(Department).where(Department.id == department_id))
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    faculty = await database.scalar(select(Faculty).where(Faculty.id == department.faculty_id))
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_membership(current_user.id, faculty.institution_id, database)
    values = list((await database.scalars(select(Course).where(Course.department_id == department_id).order_by(Course.code.asc()))).all())
    return [course_response(value) for value in values]


@router.get("/courses/{course_id}", response_model=CourseResponse, summary="Get a course")
async def get_course(course_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Course).where(Course.id == course_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Course not found")
    department = await database.scalar(select(Department).where(Department.id == value.department_id))
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    faculty = await database.scalar(select(Faculty).where(Faculty.id == department.faculty_id))
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_membership(current_user.id, faculty.institution_id, database)
    return course_response(value)


@router.patch("/courses/{course_id}", response_model=CourseResponse, summary="Update a course")
async def update_course(course_id: uuid.UUID, data: CourseCreate, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Course).where(Course.id == course_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Course not found")
    department = await database.scalar(select(Department).where(Department.id == value.department_id))
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    faculty = await database.scalar(select(Faculty).where(Faculty.id == department.faculty_id))
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_admin(current_user.id, faculty.institution_id, database)
    for field, item in data.model_dump(exclude_unset=True).items():
        setattr(value, field, item)
    value.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(value)
    return course_response(value)


@router.delete("/courses/{course_id}", status_code=204, summary="Delete a course")
async def delete_course(course_id: uuid.UUID, current_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Course).where(Course.id == course_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Course not found")
    department = await database.scalar(select(Department).where(Department.id == value.department_id))
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    faculty = await database.scalar(select(Faculty).where(Faculty.id == department.faculty_id))
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await require_institution_admin(current_user.id, faculty.institution_id, database)
    if await database.scalar(select(CourseTeacher.id).where(CourseTeacher.course_id == course_id)) is not None:
        raise HTTPException(status_code=409, detail="Course still has teacher assignments")
    if await database.scalar(select(Enrollment.id).where(Enrollment.course_id == course_id)) is not None:
        raise HTTPException(status_code=409, detail="Course still has enrollments")
    if await database.scalar(select(Lesson.id).where(Lesson.course_id == course_id)) is not None:
        raise HTTPException(status_code=409, detail="Course still has lessons")
    if await database.scalar(select(Exercise.id).join(Lesson, Lesson.id == Exercise.lesson_id).where(Lesson.course_id == course_id)) is not None:
        raise HTTPException(status_code=409, detail="Course still has exercises")
    if await database.scalar(select(Assessment.id).where(Assessment.course_id == course_id)) is not None:
        raise HTTPException(status_code=409, detail="Course still has assessments")
    if await database.scalar(select(AssessmentSubmission.id).join(Assessment, Assessment.id == AssessmentSubmission.assessment_id).where(Assessment.course_id == course_id)) is not None:
        raise HTTPException(status_code=409, detail="Course still has assessment submissions")
    if await database.scalar(select(AssessmentResult.id).join(AssessmentSubmission, AssessmentSubmission.id == AssessmentResult.submission_id).join(Assessment, Assessment.id == AssessmentSubmission.assessment_id).where(Assessment.course_id == course_id)) is not None:
        raise HTTPException(status_code=409, detail="Course still has assessment results")
    if await database.scalar(select(LessonProgress.id).join(Lesson, Lesson.id == LessonProgress.lesson_id).where(Lesson.course_id == course_id)) is not None:
        raise HTTPException(status_code=409, detail="Course still has lesson progress records")
    await database.delete(value)
    await database.commit()
