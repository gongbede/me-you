import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .lesson import Lesson


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="ck_exercises_title_not_blank"),
        CheckConstraint("length(btrim(instructions)) > 0", name="ck_exercises_instructions_not_blank"),
        CheckConstraint("position >= 0", name="ck_exercises_position_non_negative"),
        CheckConstraint("exercise_type IN ('PRACTICE', 'WRITTEN', 'PROJECT', 'OTHER')", name="ck_exercises_type"),
        Index("ix_exercises_lesson_position", "lesson_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lesson_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0)
    exercise_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_published: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    lesson: Mapped["Lesson"] = relationship(back_populates="exercises")
