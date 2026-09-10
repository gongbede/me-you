import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .lesson import Lesson
    from .student import Student


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("student_id", "lesson_id", name="uq_lesson_progress_student_lesson"),
        Index("ix_lesson_progress_student_id", "student_id"),
        Index("ix_lesson_progress_lesson_id", "lesson_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id", ondelete="RESTRICT"), nullable=False)
    lesson_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    completed: Mapped[bool] = mapped_column(nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    student: Mapped["Student"] = relationship()
    lesson: Mapped["Lesson"] = relationship()
