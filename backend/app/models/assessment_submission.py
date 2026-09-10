import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .assessment import Assessment
    from .assessment_result import AssessmentResult
    from .student import Student


class AssessmentSubmission(Base):
    __tablename__ = "assessment_submissions"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'SUBMITTED', 'GRADED')", name="ck_submissions_status"),
        CheckConstraint("status = 'DRAFT' OR length(btrim(answer_text)) > 0", name="ck_submissions_answer_when_submitted"),
        UniqueConstraint("assessment_id", "student_id", name="uq_submissions_assessment_student"),
        Index("ix_submissions_assessment_id", "assessment_id"),
        Index("ix_submissions_student_id", "student_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id", ondelete="RESTRICT"), nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")

    assessment: Mapped["Assessment"] = relationship(back_populates="submissions")
    student: Mapped["Student"] = relationship()
    result: Mapped["AssessmentResult | None"] = relationship(back_populates="submission", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
