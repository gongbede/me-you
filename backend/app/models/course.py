import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .assessment import Assessment
    from .course_teacher import CourseTeacher
    from .department import Department
    from .enrollment import Enrollment
    from .lesson import Lesson


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("length(btrim(code)) > 0", name="ck_courses_code_not_blank"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_courses_name_not_blank"),
        UniqueConstraint("department_id", "code", name="uq_courses_department_code"),
        Index("ix_courses_department_id", "department_id"),
        Index("ix_courses_code", "code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    department: Mapped["Department"] = relationship(back_populates="courses")
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="course")
    teacher_assignments: Mapped[list["CourseTeacher"]] = relationship(back_populates="course", cascade="all, delete-orphan", passive_deletes=True)
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="course", cascade="all, delete-orphan", passive_deletes=True)
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="course", cascade="all, delete-orphan", passive_deletes=True)
