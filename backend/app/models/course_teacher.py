import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .course import Course
    from .teacher import Teacher


class CourseTeacher(Base):
    __tablename__ = "course_teachers"
    __table_args__ = (
        UniqueConstraint("course_id", "teacher_id", name="uq_course_teachers_course_teacher"),
        Index("ix_course_teachers_course_id", "course_id"),
        Index("ix_course_teachers_teacher_id", "teacher_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    teacher_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    course: Mapped["Course"] = relationship(back_populates="teacher_assignments")
    teacher: Mapped["Teacher"] = relationship(back_populates="course_assignments")
