import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .institution import Institution
    from .user import User


class InstitutionMembership(Base):
    __tablename__ = "institution_memberships"
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN', 'TEACHER', 'STUDENT')", name="ck_institution_memberships_role"),
        UniqueConstraint("user_id", "institution_id", name="uq_institution_memberships_user_institution"),
        Index("ix_institution_memberships_user_id", "user_id"),
        Index("ix_institution_memberships_institution_id", "institution_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user: Mapped["User"] = relationship(back_populates="memberships")
    institution: Mapped["Institution"] = relationship(back_populates="memberships")
