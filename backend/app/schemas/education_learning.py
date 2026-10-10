from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ExerciseType = Literal["PRACTICE", "WRITTEN", "PROJECT", "OTHER"]
SubmissionStatus = Literal["DRAFT", "SUBMITTED", "GRADED"]
StudentSubmissionStatus = Literal["DRAFT", "SUBMITTED"]


def non_blank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be blank")
    return value


class CourseTeacherCreate(BaseModel):
    teacher_id: str


class CourseTeacherResponse(BaseModel):
    id: str
    course_id: str
    teacher_id: str
    created_at: datetime
    updated_at: datetime


class LessonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=50000)
    position: int = Field(default=0, ge=0)
    is_published: bool = False
    _title_not_blank = field_validator("title")(non_blank)
    _content_not_blank = field_validator("content")(non_blank)


class LessonUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, min_length=1, max_length=50000)
    position: int | None = Field(default=None, ge=0)
    is_published: bool | None = None
    _title_not_blank = field_validator("title")(lambda value: non_blank(value) if value is not None else value)
    _content_not_blank = field_validator("content")(lambda value: non_blank(value) if value is not None else value)


class LessonResponse(BaseModel):
    id: str
    course_id: str
    title: str
    content: str
    position: int
    is_published: bool
    created_at: datetime
    updated_at: datetime


class ExerciseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=20000)
    position: int = Field(default=0, ge=0)
    exercise_type: ExerciseType
    is_published: bool = False
    _title_not_blank = field_validator("title")(non_blank)
    _instructions_not_blank = field_validator("instructions")(non_blank)


class ExerciseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str | None = Field(default=None, min_length=1, max_length=20000)
    position: int | None = Field(default=None, ge=0)
    exercise_type: ExerciseType | None = None
    is_published: bool | None = None
    _title_not_blank = field_validator("title")(lambda value: non_blank(value) if value is not None else value)
    _instructions_not_blank = field_validator("instructions")(lambda value: non_blank(value) if value is not None else value)


class ExerciseResponse(BaseModel):
    id: str
    lesson_id: str
    title: str
    instructions: str
    position: int
    exercise_type: ExerciseType
    is_published: bool
    created_at: datetime
    updated_at: datetime


class ExerciseSubmissionCreate(BaseModel):
    attempt_number: int = Field(ge=1)
    answer_text: str = Field(min_length=1, max_length=50000)
    _answer_not_blank = field_validator("answer_text")(non_blank)


class ExerciseSubmissionReview(BaseModel):
    feedback: str | None = Field(default=None, max_length=20000)


class ExerciseSubmissionResponse(BaseModel):
    id: str
    exercise_id: str
    student_id: str
    attempt_number: int
    answer_text: str
    feedback: str | None
    reviewer_id: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AssessmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    instructions: str = Field(min_length=1, max_length=20000)
    max_score: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    is_published: bool = False
    due_at: datetime | None = None
    _title_not_blank = field_validator("title")(non_blank)
    _instructions_not_blank = field_validator("instructions")(non_blank)


class AssessmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    instructions: str | None = Field(default=None, min_length=1, max_length=20000)
    max_score: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    is_published: bool | None = None
    due_at: datetime | None = None


class AssessmentResponse(BaseModel):
    id: str
    course_id: str
    title: str
    instructions: str
    max_score: Decimal
    is_published: bool
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SubmissionCreate(BaseModel):
    answer_text: str = Field(min_length=1, max_length=50000)
    status: StudentSubmissionStatus = "SUBMITTED"
    _answer_not_blank = field_validator("answer_text")(non_blank)


class SubmissionUpdate(BaseModel):
    answer_text: str | None = Field(default=None, min_length=1, max_length=50000)
    status: StudentSubmissionStatus | None = None
    _answer_not_blank = field_validator("answer_text")(lambda value: non_blank(value) if value is not None else value)


class SubmissionResponse(BaseModel):
    id: str
    assessment_id: str
    student_id: str
    answer_text: str | None
    submitted_at: datetime | None
    updated_at: datetime
    status: SubmissionStatus


class ResultCreate(BaseModel):
    score: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    feedback: str | None = Field(default=None, max_length=20000)


class ResultResponse(BaseModel):
    id: str
    submission_id: str
    score: Decimal
    feedback: str | None
    graded_at: datetime
    created_at: datetime
    updated_at: datetime


class LessonProgressUpdate(BaseModel):
    completed: bool = True


class LessonProgressResponse(BaseModel):
    id: str
    student_id: str
    lesson_id: str
    completed: bool
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CourseProgressResponse(BaseModel):
    course_id: str
    completed_lessons: int
    published_lessons: int
    progress_percent: float
