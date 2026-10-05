import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ExerciseSubmission(Base):
    __tablename__ = "exercise_submissions"
    __table_args__ = (
        CheckConstraint("attempt_number > 0", name="ck_exercise_submissions_attempt_positive"),
        CheckConstraint("length(btrim(answer_text)) > 0", name="ck_exercise_submissions_answer_not_blank"),
        UniqueConstraint("exercise_id", "student_id", "attempt_number", name="uq_exercise_submissions_attempt"),
        Index("ix_exercise_submissions_exercise_id", "exercise_id"),
        Index("ix_exercise_submissions_student_id", "student_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exercise_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id", ondelete="RESTRICT"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)