import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .faculty import Faculty
    from .institution_membership import InstitutionMembership
    from .student import Student
    from .teacher import Teacher


class Institution(Base):
    __tablename__ = "institutions"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_institutions_name_not_blank"),
        CheckConstraint(
            "institution_type IN ('SCHOOL', 'UNIVERSITY', 'TRAINING_CENTER', 'MUSIC_SCHOOL', 'OTHER')",
            name="ck_institutions_type",
        ),
        Index("ix_institutions_name", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    institution_type: Mapped[str] = mapped_column(String(30), nullable=False)
    website: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    faculties: Mapped[list["Faculty"]] = relationship(back_populates="institution", cascade="all, delete-orphan", passive_deletes=True)
    memberships: Mapped[list["InstitutionMembership"]] = relationship(back_populates="institution", cascade="all, delete-orphan", passive_deletes=True)
    teachers: Mapped[list["Teacher"]] = relationship(back_populates="institution")
    students: Mapped[list["Student"]] = relationship(back_populates="institution")
