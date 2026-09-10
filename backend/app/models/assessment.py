import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .assessment_submission import AssessmentSubmission
    from .course import Course


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="ck_assessments_title_not_blank"),
        CheckConstraint("length(btrim(instructions)) > 0", name="ck_assessments_instructions_not_blank"),
        CheckConstraint("max_score > 0", name="ck_assessments_max_score_positive"),
        Index("ix_assessments_course_published", "course_id", "is_published"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    max_score: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_published: Mapped[bool] = mapped_column(nullable=False, default=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    course: Mapped["Course"] = relationship(back_populates="assessments")
    submissions: Mapped[list["AssessmentSubmission"]] = relationship(back_populates="assessment", cascade="all, delete-orphan", passive_deletes=True)
