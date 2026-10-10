import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import (
    ClassSession,
    ClassSessionAttendance,
    ClassSessionMessage,
    Enrollment,
    Notification,
    Student,
    User,
)
from ..permissions import course_institution_id, require_course_teacher, require_enrolled_student
from ..schemas import (
    ClassSessionAttendanceResponse,
    ClassSessionAttendanceUpdate,
    ClassSessionCreate,
    ClassSessionJoinResponse,
    ClassSessionMessageCreate,
    ClassSessionMessageResponse,
    ClassSessionResponse,
    ClassSessionUpdate,
)
from ..security import get_current_postgres_user


router = APIRouter(prefix="/education", tags=["classrooms"])


def value_response(value, fields: tuple[str, ...]) -> dict:
    return {
        field: str(item) if isinstance((item := getattr(value, field)), uuid.UUID) else item
        for field in fields
    }


async def session_or_404(session_id: uuid.UUID, database: AsyncSession) -> ClassSession:
    value = await database.scalar(select(ClassSession).where(ClassSession.id == session_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Class session not found")
    return value


async def session_access(session: ClassSession, user: User, database: AsyncSession) -> bool:
    await course_institution_id(session.course_id, database)
    try:
        await require_course_teacher(session.course_id, user.id, database)
        return True
    except HTTPException as error:
        if error.status_code != status.HTTP_403_FORBIDDEN:
            raise
    await require_enrolled_student(session.course_id, user.id, database)
    return False


def session_response(value: ClassSession) -> dict:
    return value_response(
        value,
        (
            "id", "course_id", "created_by_id", "title", "description", "starts_at",
            "ends_at", "status", "started_at", "ended_at", "created_at", "updated_at",
        ),
    )


@router.post("/courses/{course_id}/class-sessions", response_model=ClassSessionResponse, status_code=201, summary="Schedule a live classroom")
async def create_class_session(course_id: uuid.UUID, data: ClassSessionCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await require_course_teacher(course_id, current_user.id, database)
    value = ClassSession(course_id=course_id, created_by_id=current_user.id, status="SCHEDULED", **data.model_dump())
    database.add(value)
    await database.flush()
    student_ids = await database.scalars(
        select(Student.user_id)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.course_id == course_id)
    )
    now = datetime.now(timezone.utc)
    database.add_all([
        ClassSessionAttendance(session_id=value.id, user_id=user_id, status="ABSENT", updated_at=now)
        for user_id in student_ids.all()
    ])
    await database.commit()
    await database.refresh(value)
    return session_response(value)


@router.get("/courses/{course_id}/class-sessions", response_model=list[ClassSessionResponse], summary="List course classroom sessions")
async def list_class_sessions(course_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session), offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    await course_institution_id(course_id, database)
    try:
        await require_course_teacher(course_id, current_user.id, database)
        is_teacher = True
    except HTTPException as error:
        if error.status_code != status.HTTP_403_FORBIDDEN:
            raise
        await require_enrolled_student(course_id, current_user.id, database)
        is_teacher = False
    statement = select(ClassSession).where(ClassSession.course_id == course_id)
    if not is_teacher:
        statement = statement.where(ClassSession.status != "CANCELLED")
    values = list((await database.scalars(statement.order_by(ClassSession.starts_at.desc(), ClassSession.id.desc()).offset(offset).limit(limit))).all())
    return [session_response(value) for value in values]


@router.get("/class-sessions/{session_id}", response_model=ClassSessionResponse, summary="Get a classroom session")
async def get_class_session(session_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await session_or_404(session_id, database)
    await session_access(value, current_user, database)
    return session_response(value)


@router.patch("/class-sessions/{session_id}", response_model=ClassSessionResponse, summary="Update a scheduled classroom")
async def update_class_session(session_id: uuid.UUID, data: ClassSessionUpdate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await session_or_404(session_id, database)
    await require_course_teacher(value.course_id, current_user.id, database)
    if value.status != "SCHEDULED":
        raise HTTPException(status_code=409, detail="Only scheduled classrooms may be edited")
    updates = data.model_dump(exclude_unset=True)
    starts_at = updates.get("starts_at", value.starts_at)
    ends_at = updates.get("ends_at", value.ends_at)
    if starts_at.tzinfo is None or ends_at.tzinfo is None or ends_at <= starts_at:
        raise HTTPException(status_code=422, detail="Classroom times must include a timezone and end after they start")
    for field, item in updates.items():
        setattr(value, field, item)
    value.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(value)
    return session_response(value)


async def change_session_status(session_id: uuid.UUID, current_user: User, database: AsyncSession, *, action: str) -> dict:
    value = await session_or_404(session_id, database)
    await require_course_teacher(value.course_id, current_user.id, database)
    now = datetime.now(timezone.utc)
    if action == "start" and value.status == "SCHEDULED":
        value.status = "LIVE"
        value.started_at = now
    elif action == "end" and value.status == "LIVE":
        value.status = "ENDED"
        value.ended_at = now
    elif action == "cancel" and value.status == "SCHEDULED":
        value.status = "CANCELLED"
    else:
        raise HTTPException(status_code=409, detail=f"Classroom cannot be {action}ed from {value.status.lower()} state")
    value.updated_at = now
    await database.commit()
    await database.refresh(value)
    return session_response(value)


@router.post("/class-sessions/{session_id}/start", response_model=ClassSessionResponse, summary="Start a classroom")
async def start_class_session(session_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    return await change_session_status(session_id, current_user, database, action="start")


@router.post("/class-sessions/{session_id}/end", response_model=ClassSessionResponse, summary="End a classroom")
async def end_class_session(session_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    return await change_session_status(session_id, current_user, database, action="end")


@router.post("/class-sessions/{session_id}/cancel", response_model=ClassSessionResponse, summary="Cancel a scheduled classroom")
async def cancel_class_session(session_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    return await change_session_status(session_id, current_user, database, action="cancel")


@router.post("/class-sessions/{session_id}/join", response_model=ClassSessionJoinResponse, summary="Join a live classroom")
async def join_class_session(session_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await session_or_404(session_id, database)
    if value.status != "LIVE":
        raise HTTPException(status_code=409, detail="This classroom is not live")
    is_teacher = await session_access(value, current_user, database)
    now = datetime.now(timezone.utc)
    status_value = "PRESENT" if is_teacher or now <= value.starts_at + timedelta(minutes=10) else "LATE"
    attendance = await database.scalar(
        select(ClassSessionAttendance)
        .where(ClassSessionAttendance.session_id == value.id, ClassSessionAttendance.user_id == current_user.id)
        .with_for_update()
    )
    if attendance is None:
        attendance = ClassSessionAttendance(session_id=value.id, user_id=current_user.id, status=status_value, joined_at=now, updated_at=now)
        database.add(attendance)
    else:
        attendance.status = status_value
        attendance.joined_at = attendance.joined_at or now
        attendance.updated_at = now
    await database.commit()
    return {"session_id": str(value.id), "user_id": str(current_user.id), "status": attendance.status, "joined_at": attendance.joined_at}


@router.get("/class-sessions/{session_id}/attendance", response_model=list[ClassSessionAttendanceResponse], summary="List classroom attendance")
async def list_class_session_attendance(session_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await session_or_404(session_id, database)
    await require_course_teacher(value.course_id, current_user.id, database)
    rows = (
        await database.execute(
            select(User.id, User.username, ClassSessionAttendance.status, ClassSessionAttendance.joined_at, ClassSessionAttendance.updated_at)
            .join(Student, Student.user_id == User.id)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .outerjoin(
                ClassSessionAttendance,
                (ClassSessionAttendance.session_id == value.id) & (ClassSessionAttendance.user_id == User.id),
            )
            .where(Enrollment.course_id == value.course_id)
            .order_by(User.username.asc(), User.id.asc())
        )
    ).all()
    return [
        {
            "session_id": str(value.id),
            "user_id": str(user_id),
            "username": username,
            "status": attendance_status or "ABSENT",
            "joined_at": joined_at,
            "updated_at": updated_at or value.created_at,
        }
        for user_id, username, attendance_status, joined_at, updated_at in rows
    ]


@router.patch("/class-sessions/{session_id}/attendance", response_model=ClassSessionAttendanceResponse, summary="Mark classroom attendance")
async def update_class_session_attendance(session_id: uuid.UUID, data: ClassSessionAttendanceUpdate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await session_or_404(session_id, database)
    await require_course_teacher(value.course_id, current_user.id, database)
    try:
        user_id = uuid.UUID(data.user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="user_id must be a UUID") from None
    username = await database.scalar(
        select(User.username)
        .join(Student, Student.user_id == User.id)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(User.id == user_id, Enrollment.course_id == value.course_id)
    )
    if username is None:
        raise HTTPException(status_code=404, detail="Enrolled student not found")
    now = datetime.now(timezone.utc)
    attendance = await database.scalar(
        select(ClassSessionAttendance)
        .where(ClassSessionAttendance.session_id == value.id, ClassSessionAttendance.user_id == user_id)
        .with_for_update()
    )
    if attendance is None:
        attendance = ClassSessionAttendance(session_id=value.id, user_id=user_id, status=data.status, marked_by_id=current_user.id, updated_at=now)
        database.add(attendance)
    else:
        attendance.status = data.status
        attendance.marked_by_id = current_user.id
        attendance.updated_at = now
    await database.commit()
    return {
        "session_id": str(value.id), "user_id": str(user_id), "username": username,
        "status": attendance.status, "joined_at": attendance.joined_at, "updated_at": attendance.updated_at,
    }


@router.get("/class-sessions/{session_id}/messages", response_model=list[ClassSessionMessageResponse], summary="List classroom chat and announcements")
async def list_class_session_messages(session_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session), offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    value = await session_or_404(session_id, database)
    await session_access(value, current_user, database)
    rows = (
        await database.execute(
            select(ClassSessionMessage, User.username)
            .join(User, User.id == ClassSessionMessage.sender_id)
            .where(ClassSessionMessage.session_id == value.id)
            .order_by(ClassSessionMessage.created_at.asc(), ClassSessionMessage.id.asc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [
        {
            **value_response(message, ("id", "session_id", "sender_id", "message_type", "content", "created_at")),
            "sender_name": username,
        }
        for message, username in rows
    ]


@router.post("/class-sessions/{session_id}/messages", response_model=ClassSessionMessageResponse, status_code=201, summary="Send classroom chat or an announcement")
async def create_class_session_message(session_id: uuid.UUID, data: ClassSessionMessageCreate, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    value = await session_or_404(session_id, database)
    is_teacher = await session_access(value, current_user, database)
    if value.status in {"ENDED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="This classroom is closed")
    if data.message_type == "ANNOUNCEMENT" and not is_teacher:
        raise HTTPException(status_code=403, detail="Only the assigned teacher may post announcements")
    if data.message_type == "CHAT" and value.status != "LIVE":
        raise HTTPException(status_code=409, detail="Chat is available while the classroom is live")
    now = datetime.now(timezone.utc)
    message = ClassSessionMessage(
        session_id=value.id,
        sender_id=current_user.id,
        message_type=data.message_type,
        content=data.content,
        created_at=now,
    )
    database.add(message)
    if data.message_type == "ANNOUNCEMENT":
        student_user_ids = await database.scalars(
            select(Student.user_id)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(Enrollment.course_id == value.course_id)
        )
        database.add_all([
            Notification(
                recipient_id=user_id,
                actor_id=current_user.id,
                type="CLASS_ANNOUNCEMENT",
                title="Classroom announcement",
                payload={"session_id": str(value.id)},
                target_type="class_session",
                target_id=value.id,
            )
            for user_id in student_user_ids.all()
            if user_id != current_user.id
        ])
    await database.commit()
    await database.refresh(message)
    return {
        **value_response(message, ("id", "session_id", "sender_id", "message_type", "content", "created_at")),
        "sender_name": current_user.username,
    }