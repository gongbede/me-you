import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
    Lesson,
    LessonProgress,
    Student,
    Teacher,
    User,
)
from ..schemas import (
    AssessmentCreate,
    AssessmentResponse,
    AssessmentUpdate,
    CourseProgressResponse,
    CourseTeacherCreate,
    CourseTeacherResponse,
    ExerciseCreate,
    ExerciseResponse,
    ExerciseUpdate,
    LessonCreate,
    LessonProgressResponse,
    LessonProgressUpdate,
    LessonResponse,
    LessonUpdate,
    ResultCreate,
    ResultResponse,
    SubmissionCreate,
    SubmissionResponse,
    SubmissionUpdate,
)
from ..security import get_current_postgres_user


router = APIRouter(prefix="/education", tags=["education-learning"])


def response_value(value, fields: tuple[str, ...]) -> dict:
    result = {}
    for field in fields:
        item = getattr(value, field)
        result[field] = str(item) if isinstance(item, uuid.UUID) else item
    return result


def parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} must be a UUID") from None


async def course_or_404(course_id: uuid.UUID, database: AsyncSession) -> Course:
    course = await database.scalar(select(Course).where(Course.id == course_id))
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


async def lesson_or_404(lesson_id: uuid.UUID, database: AsyncSession) -> Lesson:
    lesson = await database.scalar(select(Lesson).where(Lesson.id == lesson_id))
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


async def exercise_or_404(exercise_id: uuid.UUID, database: AsyncSession) -> Exercise:
    exercise = await database.scalar(select(Exercise).where(Exercise.id == exercise_id))
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise


async def assessment_or_404(assessment_id: uuid.UUID, database: AsyncSession) -> Assessment:
    assessment = await database.scalar(select(Assessment).where(Assessment.id == assessment_id))
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


async def teacher_for_user(user_id: uuid.UUID, teacher_id: uuid.UUID, database: AsyncSession) -> Teacher:
    teacher = await database.scalar(select(Teacher).where(Teacher.id == teacher_id, Teacher.user_id == user_id))
    if teacher is None:
        raise HTTPException(status_code=403, detail="Teacher membership required")
    return teacher


async def course_institution_id(course_id: uuid.UUID, database: AsyncSession) -> uuid.UUID:
    value = await database.scalar(
        select(Faculty.institution_id)
        .join(Department, Department.faculty_id == Faculty.id)
        .join(Course, Course.department_id == Department.id)
        .where(Course.id == course_id)
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return value


async def assigned_teacher(course_id: uuid.UUID, user_id: uuid.UUID, database: AsyncSession) -> Teacher:
    teacher = await database.scalar(
        select(Teacher)
        .join(CourseTeacher, CourseTeacher.teacher_id == Teacher.id)
        .where(CourseTeacher.course_id == course_id, Teacher.user_id == user_id)
    )
    if teacher is None:
        raise HTTPException(status_code=403, detail="Assigned teacher access required")
    return teacher


async def student_for_course(course_id: uuid.UUID, user_id: uuid.UUID, database: AsyncSession) -> Student:
    student = await database.scalar(
        select(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.course_id == course_id, Student.user_id == user_id)
    )
    if student is None:
        raise HTTPException(status_code=403, detail="Course enrollment required")
    return student


async def accessible_lesson(lesson: Lesson, user_id: uuid.UUID, database: AsyncSession) -> Student:
    if not lesson.is_published:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return await student_for_course(lesson.course_id, user_id, database)


def lesson_response(value: Lesson) -> dict:
    return response_value(value, ("id", "course_id", "title", "content", "position", "is_published", "created_at", "updated_at"))


def exercise_response(value: Exercise) -> dict:
    return response_value(value, ("id", "lesson_id", "title", "instructions", "position", "exercise_type", "created_at", "updated_at"))


def assessment_response(value: Assessment) -> dict:
    return response_value(value, ("id", "course_id", "title", "instructions", "max_score", "is_published", "due_at", "created_at", "updated_at"))


def submission_response(value: AssessmentSubmission) -> dict:
    return response_value(value, ("id", "assessment_id", "student_id", "answer_text", "submitted_at", "updated_at", "status"))


def result_response(value: AssessmentResult) -> dict:
    return response_value(value, ("id", "submission_id", "score", "feedback", "graded_at", "created_at", "updated_at"))


def progress_response(value: LessonProgress) -> dict:
    return response_value(value, ("id", "student_id", "lesson_id", "completed", "completed_at", "created_at", "updated_at"))


@router.post("/courses/{course_id}/teachers", response_model=CourseTeacherResponse, status_code=201, summary="Assign a teacher to a course")
async def assign_teacher(course_id: uuid.UUID, data: CourseTeacherCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    institution_id = await course_institution_id(course_id, database)
    teacher_id = parse_uuid(data.teacher_id, "teacher_id")
    teacher = await database.scalar(select(Teacher).where(Teacher.id == teacher_id, Teacher.institution_id == institution_id))
    if teacher is None:
        raise HTTPException(status_code=404, detail="Teacher not found in course institution")
    if teacher.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the teacher can assign their own teaching record")
    value = CourseTeacher(course_id=course_id, teacher_id=teacher_id)
    database.add(value)
    try:
        await database.commit()
        await database.refresh(value)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="Teacher is already assigned") from None
    return response_value(value, ("id", "course_id", "teacher_id", "created_at", "updated_at"))


@router.get("/courses/{course_id}/teachers", response_model=list[CourseTeacherResponse], summary="List course teachers")
async def list_course_teachers(course_id: uuid.UUID, _user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await course_or_404(course_id, database)
    values = list((await database.scalars(select(CourseTeacher).where(CourseTeacher.course_id == course_id))).all())
    return [response_value(value, ("id", "course_id", "teacher_id", "created_at", "updated_at")) for value in values]


@router.delete("/courses/{course_id}/teachers/{teacher_id}", status_code=204, summary="Remove a course teacher")
async def remove_teacher(course_id: uuid.UUID, teacher_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await assigned_teacher(course_id, current_user.id, database)
    value = await database.scalar(select(CourseTeacher).where(CourseTeacher.course_id == course_id, CourseTeacher.teacher_id == teacher_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Course teacher assignment not found")
    await database.delete(value)
    await database.commit()


@router.post("/courses/{course_id}/lessons", response_model=LessonResponse, status_code=201, summary="Create a lesson")
async def create_lesson(course_id: uuid.UUID, data: LessonCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await assigned_teacher(course_id, current_user.id, database)
    value = Lesson(course_id=course_id, **data.model_dump())
    database.add(value)
    await database.commit()
    await database.refresh(value)
    return lesson_response(value)


@router.get("/courses/{course_id}/lessons", response_model=list[LessonResponse], summary="List course lessons")
async def list_lessons(course_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await course_or_404(course_id, database)
    teacher = await database.scalar(select(Teacher).join(CourseTeacher, CourseTeacher.teacher_id == Teacher.id).where(CourseTeacher.course_id == course_id, Teacher.user_id == current_user.id))
    if teacher is None:
        await student_for_course(course_id, current_user.id, database)
        statement = select(Lesson).where(Lesson.course_id == course_id, Lesson.is_published.is_(True))
    else:
        statement = select(Lesson).where(Lesson.course_id == course_id)
    values = list((await database.scalars(statement.order_by(Lesson.position.asc(), Lesson.id.asc()))).all())
    return [lesson_response(value) for value in values]


@router.get("/lessons/{lesson_id}", response_model=LessonResponse, summary="Get a lesson")
async def get_lesson(lesson_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    lesson = await lesson_or_404(lesson_id, database)
    if lesson.is_published:
        await student_for_course(lesson.course_id, current_user.id, database)
    else:
        await assigned_teacher(lesson.course_id, current_user.id, database)
    return lesson_response(lesson)


@router.patch("/lessons/{lesson_id}", response_model=LessonResponse, summary="Update a lesson")
async def update_lesson(lesson_id: uuid.UUID, data: LessonUpdate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    lesson = await lesson_or_404(lesson_id, database)
    await assigned_teacher(lesson.course_id, current_user.id, database)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(lesson, field, value)
    lesson.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(lesson)
    return lesson_response(lesson)


@router.delete("/lessons/{lesson_id}", status_code=204, summary="Delete a lesson")
async def delete_lesson(lesson_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    lesson = await lesson_or_404(lesson_id, database)
    await assigned_teacher(lesson.course_id, current_user.id, database)
    await database.delete(lesson)
    await database.commit()


@router.post("/lessons/{lesson_id}/exercises", response_model=ExerciseResponse, status_code=201, summary="Create an exercise")
async def create_exercise(lesson_id: uuid.UUID, data: ExerciseCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    lesson = await lesson_or_404(lesson_id, database)
    await assigned_teacher(lesson.course_id, current_user.id, database)
    value = Exercise(lesson_id=lesson_id, **data.model_dump())
    database.add(value)
    await database.commit()
    await database.refresh(value)
    return exercise_response(value)


@router.get("/lessons/{lesson_id}/exercises", response_model=list[ExerciseResponse], summary="List lesson exercises")
async def list_exercises(lesson_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    lesson = await lesson_or_404(lesson_id, database)
    await accessible_lesson(lesson, current_user.id, database)
    values = list((await database.scalars(select(Exercise).where(Exercise.lesson_id == lesson_id).order_by(Exercise.position.asc(), Exercise.id.asc()))).all())
    return [exercise_response(value) for value in values]


@router.get("/exercises/{exercise_id}", response_model=ExerciseResponse, summary="Get an exercise")
async def get_exercise(exercise_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await exercise_or_404(exercise_id, database)
    lesson = await lesson_or_404(value.lesson_id, database)
    if lesson.is_published:
        await accessible_lesson(lesson, current_user.id, database)
    else:
        await assigned_teacher(lesson.course_id, current_user.id, database)
    return exercise_response(value)


@router.patch("/exercises/{exercise_id}", response_model=ExerciseResponse, summary="Update an exercise")
async def update_exercise(exercise_id: uuid.UUID, data: ExerciseUpdate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await exercise_or_404(exercise_id, database)
    lesson = await lesson_or_404(value.lesson_id, database)
    await assigned_teacher(lesson.course_id, current_user.id, database)
    for field, item in data.model_dump(exclude_unset=True).items():
        setattr(value, field, item)
    value.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(value)
    return exercise_response(value)


@router.delete("/exercises/{exercise_id}", status_code=204, summary="Delete an exercise")
async def delete_exercise(exercise_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await exercise_or_404(exercise_id, database)
    lesson = await lesson_or_404(value.lesson_id, database)
    await assigned_teacher(lesson.course_id, current_user.id, database)
    await database.delete(value)
    await database.commit()


@router.post("/courses/{course_id}/assessments", response_model=AssessmentResponse, status_code=201, summary="Create an assessment")
async def create_assessment(course_id: uuid.UUID, data: AssessmentCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await assigned_teacher(course_id, current_user.id, database)
    value = Assessment(course_id=course_id, **data.model_dump())
    database.add(value)
    await database.commit()
    await database.refresh(value)
    return assessment_response(value)


@router.get("/courses/{course_id}/assessments", response_model=list[AssessmentResponse], summary="List course assessments")
async def list_assessments(course_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await course_or_404(course_id, database)
    teacher = await database.scalar(select(Teacher).join(CourseTeacher, CourseTeacher.teacher_id == Teacher.id).where(CourseTeacher.course_id == course_id, Teacher.user_id == current_user.id))
    if teacher is None:
        await student_for_course(course_id, current_user.id, database)
        statement = select(Assessment).where(Assessment.course_id == course_id, Assessment.is_published.is_(True))
    else:
        statement = select(Assessment).where(Assessment.course_id == course_id)
    values = list((await database.scalars(statement.order_by(Assessment.created_at.asc()))).all())
    return [assessment_response(value) for value in values]


@router.get("/assessments/{assessment_id}", response_model=AssessmentResponse, summary="Get an assessment")
async def get_assessment(assessment_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await assessment_or_404(assessment_id, database)
    if value.is_published:
        await student_for_course(value.course_id, current_user.id, database)
    else:
        await assigned_teacher(value.course_id, current_user.id, database)
    return assessment_response(value)


@router.patch("/assessments/{assessment_id}", response_model=AssessmentResponse, summary="Update an assessment")
async def update_assessment(assessment_id: uuid.UUID, data: AssessmentUpdate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await assessment_or_404(assessment_id, database)
    await assigned_teacher(value.course_id, current_user.id, database)
    for field, item in data.model_dump(exclude_unset=True).items():
        setattr(value, field, item)
    value.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(value)
    return assessment_response(value)


@router.delete("/assessments/{assessment_id}", status_code=204, summary="Delete an assessment")
async def delete_assessment(assessment_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await assessment_or_404(assessment_id, database)
    await assigned_teacher(value.course_id, current_user.id, database)
    await database.delete(value)
    await database.commit()


@router.post("/assessments/{assessment_id}/submissions", response_model=SubmissionResponse, status_code=201, summary="Submit an assessment")
async def create_submission(assessment_id: uuid.UUID, data: SubmissionCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    assessment = await assessment_or_404(assessment_id, database)
    student = await student_for_course(assessment.course_id, current_user.id, database)
    if not assessment.is_published:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if assessment.due_at and datetime.now(timezone.utc) > assessment.due_at:
        raise HTTPException(status_code=422, detail="Assessment due date has passed")
    value = AssessmentSubmission(assessment_id=assessment_id, student_id=student.id, answer_text=data.answer_text, status=data.status, submitted_at=datetime.now(timezone.utc) if data.status == "SUBMITTED" else None)
    database.add(value)
    try:
        await database.commit()
        await database.refresh(value)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="Submission already exists") from None
    return submission_response(value)


@router.get("/assessments/{assessment_id}/submissions", response_model=list[SubmissionResponse], summary="List assessment submissions")
async def list_submissions(assessment_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    assessment = await assessment_or_404(assessment_id, database)
    await assigned_teacher(assessment.course_id, current_user.id, database)
    values = list((await database.scalars(select(AssessmentSubmission).where(AssessmentSubmission.assessment_id == assessment_id))).all())
    return [submission_response(value) for value in values]


@router.get("/submissions/{submission_id}", response_model=SubmissionResponse, summary="Get a submission")
async def get_submission(submission_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(AssessmentSubmission).where(AssessmentSubmission.id == submission_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    student = await database.scalar(select(Student).where(Student.id == value.student_id))
    if student.user_id != current_user.id:
        assessment = await assessment_or_404(value.assessment_id, database)
        await assigned_teacher(assessment.course_id, current_user.id, database)
    return submission_response(value)


@router.patch("/submissions/{submission_id}", response_model=SubmissionResponse, summary="Update your submission")
async def update_submission(submission_id: uuid.UUID, data: SubmissionUpdate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(AssessmentSubmission).where(AssessmentSubmission.id == submission_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    student = await database.scalar(select(Student).where(Student.id == value.student_id))
    if student.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the submission owner may modify it")
    if value.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft submissions may be modified")
    for field, item in data.model_dump(exclude_unset=True).items():
        setattr(value, field, item)
    value.updated_at = datetime.now(timezone.utc)
    if value.status == "SUBMITTED":
        value.submitted_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(value)
    return submission_response(value)


@router.post("/submissions/{submission_id}/result", response_model=ResultResponse, status_code=201, summary="Record an assessment result")
async def create_result(submission_id: uuid.UUID, data: ResultCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    submission = await database.scalar(select(AssessmentSubmission).where(AssessmentSubmission.id == submission_id))
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    assessment = await assessment_or_404(submission.assessment_id, database)
    await assigned_teacher(assessment.course_id, current_user.id, database)
    if data.score > assessment.max_score:
        raise HTTPException(status_code=422, detail="Score cannot exceed max_score")
    value = AssessmentResult(submission_id=submission_id, score=data.score, feedback=data.feedback)
    database.add(value)
    submission.status = "GRADED"
    try:
        await database.commit()
        await database.refresh(value)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="Assessment result already exists") from None
    return result_response(value)


@router.get("/submissions/{submission_id}/result", response_model=ResultResponse, summary="Get an assessment result")
async def get_result(submission_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(AssessmentResult).where(AssessmentResult.submission_id == submission_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Assessment result not found")
    submission = await database.scalar(select(AssessmentSubmission).where(AssessmentSubmission.id == submission_id))
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    student = await database.scalar(select(Student).where(Student.id == submission.student_id))
    if student.user_id != current_user.id:
        assessment = await assessment_or_404(submission.assessment_id, database)
        await assigned_teacher(assessment.course_id, current_user.id, database)
    return result_response(value)


@router.patch("/submissions/{submission_id}/result", response_model=ResultResponse, summary="Update an assessment result")
async def update_result(submission_id: uuid.UUID, data: ResultCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await database.scalar(select(AssessmentResult).where(AssessmentResult.submission_id == submission_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Assessment result not found")
    submission = await database.scalar(select(AssessmentSubmission).where(AssessmentSubmission.id == submission_id))
    assessment = await assessment_or_404(submission.assessment_id, database)
    await assigned_teacher(assessment.course_id, current_user.id, database)
    if data.score > assessment.max_score:
        raise HTTPException(status_code=422, detail="Score cannot exceed max_score")
    value.score = data.score
    value.feedback = data.feedback
    value.updated_at = datetime.now(timezone.utc)
    value.graded_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(value)
    return result_response(value)


@router.post("/lessons/{lesson_id}/progress", response_model=LessonProgressResponse, summary="Update lesson progress")
async def update_progress(lesson_id: uuid.UUID, data: LessonProgressUpdate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    lesson = await lesson_or_404(lesson_id, database)
    student = await student_for_course(lesson.course_id, current_user.id, database)
    value = await database.scalar(select(LessonProgress).where(LessonProgress.student_id == student.id, LessonProgress.lesson_id == lesson_id))
    now = datetime.now(timezone.utc)
    if value is None:
        value = LessonProgress(student_id=student.id, lesson_id=lesson_id, completed=data.completed, completed_at=now if data.completed else None, created_at=now, updated_at=now)
        database.add(value)
    else:
        value.completed = data.completed
        value.completed_at = now if data.completed else None
        value.updated_at = now
    await database.commit()
    await database.refresh(value)
    return progress_response(value)


@router.get("/lessons/{lesson_id}/progress", response_model=LessonProgressResponse, summary="Get lesson progress")
async def get_progress(lesson_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    lesson = await lesson_or_404(lesson_id, database)
    student = await student_for_course(lesson.course_id, current_user.id, database)
    value = await database.scalar(select(LessonProgress).where(LessonProgress.student_id == student.id, LessonProgress.lesson_id == lesson_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Lesson progress not found")
    return progress_response(value)


@router.get("/courses/{course_id}/progress", response_model=CourseProgressResponse, summary="Get course progress")
async def get_course_progress(course_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await course_or_404(course_id, database)
    student = await student_for_course(course_id, current_user.id, database)
    published = await database.scalar(select(func.count(Lesson.id)).where(Lesson.course_id == course_id, Lesson.is_published.is_(True)))
    completed = await database.scalar(select(func.count(LessonProgress.id)).join(Lesson, Lesson.id == LessonProgress.lesson_id).where(LessonProgress.student_id == student.id, LessonProgress.completed.is_(True), Lesson.course_id == course_id, Lesson.is_published.is_(True)))
    published_count = int(published or 0)
    completed_count = int(completed or 0)
    return {"course_id": str(course_id), "completed_lessons": completed_count, "published_lessons": published_count, "progress_percent": (completed_count / published_count * 100) if published_count else 0.0}
