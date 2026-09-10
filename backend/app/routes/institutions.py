import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import Course, Department, Faculty, Institution
from ..schemas import (
    CourseCreate,
    CourseResponse,
    DepartmentCreate,
    DepartmentResponse,
    FacultyCreate,
    FacultyResponse,
    InstitutionCreate,
    InstitutionResponse,
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


@router.post("", response_model=InstitutionResponse, status_code=201, summary="Create an institution")
async def create_institution(data: InstitutionCreate, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    institution = Institution(**data.model_dump(), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    database.add(institution)
    await database.commit()
    await database.refresh(institution)
    return institution_response(institution)


@router.get("", response_model=list[InstitutionResponse], summary="List institutions")
async def list_institutions(_user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    values = list((await database.scalars(select(Institution).order_by(Institution.name.asc()))).all())
    return [institution_response(value) for value in values]


@router.get("/{institution_id}", response_model=InstitutionResponse, summary="Get an institution")
async def get_institution(institution_id: uuid.UUID, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Institution).where(Institution.id == institution_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    return institution_response(value)


@router.post("/{institution_id}/faculties", response_model=FacultyResponse, status_code=201, summary="Create a faculty")
async def create_faculty(institution_id: uuid.UUID, data: FacultyCreate, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    if await database.scalar(select(Institution.id).where(Institution.id == institution_id)) is None:
        raise HTTPException(status_code=404, detail="Institution not found")
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
async def list_faculties(institution_id: uuid.UUID, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    if await database.scalar(select(Institution.id).where(Institution.id == institution_id)) is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    values = list((await database.scalars(select(Faculty).where(Faculty.institution_id == institution_id).order_by(Faculty.name.asc()))).all())
    return [faculty_response(value) for value in values]


@router.get("/faculties/{faculty_id}", response_model=FacultyResponse, summary="Get a faculty")
async def get_faculty(faculty_id: uuid.UUID, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Faculty).where(Faculty.id == faculty_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return faculty_response(value)


@router.post("/faculties/{faculty_id}/departments", response_model=DepartmentResponse, status_code=201, summary="Create a department")
async def create_department(faculty_id: uuid.UUID, data: DepartmentCreate, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    if await database.scalar(select(Faculty.id).where(Faculty.id == faculty_id)) is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
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
async def get_department(department_id: uuid.UUID, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Department).where(Department.id == department_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return department_response(value)


@router.get("/faculties/{faculty_id}/departments", response_model=list[DepartmentResponse], summary="List faculty departments")
async def list_departments(faculty_id: uuid.UUID, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    if await database.scalar(select(Faculty.id).where(Faculty.id == faculty_id)) is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    values = list((await database.scalars(select(Department).where(Department.faculty_id == faculty_id).order_by(Department.name.asc()))).all())
    return [department_response(value) for value in values]


@router.post("/departments/{department_id}/courses", response_model=CourseResponse, status_code=201, summary="Create a course")
async def create_course(department_id: uuid.UUID, data: CourseCreate, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    if await database.scalar(select(Department.id).where(Department.id == department_id)) is None:
        raise HTTPException(status_code=404, detail="Department not found")
    value = Course(department_id=department_id, **data.model_dump())
    database.add(value)
    try:
        await database.commit()
        await database.refresh(value)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="Course code already exists in this department") from None
    return course_response(value)


@router.get("/departments/{department_id}/courses", response_model=list[CourseResponse], summary="List department courses")
async def list_courses(department_id: uuid.UUID, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    if await database.scalar(select(Department.id).where(Department.id == department_id)) is None:
        raise HTTPException(status_code=404, detail="Department not found")
    values = list((await database.scalars(select(Course).where(Course.department_id == department_id).order_by(Course.code.asc()))).all())
    return [course_response(value) for value in values]


@router.get("/courses/{course_id}", response_model=CourseResponse, summary="Get a course")
async def get_course(course_id: uuid.UUID, _user=Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(Course).where(Course.id == course_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course_response(value)
