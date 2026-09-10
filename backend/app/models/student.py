import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .institution import Institution
    from .user import User
    from .enrollment import Enrollment


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("user_id", "institution_id", name="uq_students_user_institution"),
        Index("ix_students_user_id", "user_id"),
        Index("ix_students_institution_id", "institution_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user: Mapped["User"] = relationship(back_populates="student_records")
    institution: Mapped["Institution"] = relationship(back_populates="students")
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="student")
