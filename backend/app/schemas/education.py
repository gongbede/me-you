from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


InstitutionType = Literal["SCHOOL", "UNIVERSITY", "TRAINING_CENTER", "MUSIC_SCHOOL", "OTHER"]


def non_blank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be blank")
    return value


class InstitutionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    institution_type: InstitutionType
    website: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=200)
    _name_not_blank = field_validator("name")(non_blank)


class InstitutionResponse(BaseModel):
    id: str
    name: str
    description: str | None
    institution_type: InstitutionType
    website: str | None
    location: str | None
    created_at: datetime
    updated_at: datetime


class FacultyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    _name_not_blank = field_validator("name")(non_blank)


class FacultyResponse(BaseModel):
    id: str
    institution_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    _name_not_blank = field_validator("name")(non_blank)


class DepartmentResponse(BaseModel):
    id: str
    faculty_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class CourseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    _code_not_blank = field_validator("code")(non_blank)
    _name_not_blank = field_validator("name")(non_blank)


class CourseResponse(BaseModel):
    id: str
    department_id: str
    code: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class StudentCreate(BaseModel):
    institution_id: str


class StudentResponse(BaseModel):
    id: str
    user_id: str
    institution_id: str
    created_at: datetime
    updated_at: datetime


class TeacherCreate(BaseModel):
    institution_id: str


class TeacherResponse(BaseModel):
    id: str
    user_id: str
    institution_id: str
    created_at: datetime
    updated_at: datetime


class EnrollmentCreate(BaseModel):
    course_id: str


class EnrollmentResponse(BaseModel):
    id: str
    student_id: str
    course_id: str
    created_at: datetime
    updated_at: datetime
