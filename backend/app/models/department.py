import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .course import Course
    from .faculty import Faculty


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_departments_name_not_blank"),
        UniqueConstraint("faculty_id", "name", name="uq_departments_faculty_name"),
        Index("ix_departments_faculty_id", "faculty_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    faculty_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("faculties.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    faculty: Mapped["Faculty"] = relationship(back_populates="departments")
    courses: Mapped[list["Course"]] = relationship(back_populates="department", cascade="all, delete-orphan", passive_deletes=True)
