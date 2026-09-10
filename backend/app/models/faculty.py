import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .department import Department
    from .institution import Institution


class Faculty(Base):
    __tablename__ = "faculties"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_faculties_name_not_blank"),
        UniqueConstraint("institution_id", "name", name="uq_faculties_institution_name"),
        Index("ix_faculties_institution_id", "institution_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    institution: Mapped["Institution"] = relationship(back_populates="faculties")
    departments: Mapped[list["Department"]] = relationship(back_populates="faculty", cascade="all, delete-orphan", passive_deletes=True)
