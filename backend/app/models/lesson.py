import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .course import Course
    from .exercise import Exercise


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="ck_lessons_title_not_blank"),
        CheckConstraint("length(btrim(content)) > 0", name="ck_lessons_content_not_blank"),
        CheckConstraint("position >= 0", name="ck_lessons_position_non_negative"),
        Index("ix_lessons_course_position", "course_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    course: Mapped["Course"] = relationship(back_populates="lessons")
    exercises: Mapped[list["Exercise"]] = relationship(back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True)
