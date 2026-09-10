import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .assessment_submission import AssessmentSubmission


class AssessmentResult(Base):
    __tablename__ = "assessment_results"
    __table_args__ = (
        CheckConstraint("score >= 0", name="ck_results_score_non_negative"),
        UniqueConstraint("submission_id", name="uq_results_submission"),
        Index("ix_results_submission_id", "submission_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assessment_submissions.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    submission: Mapped["AssessmentSubmission"] = relationship(back_populates="result")
