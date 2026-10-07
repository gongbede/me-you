import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class InstitutionMembershipRequest(Base):
    __tablename__ = "institution_membership_requests"
    __table_args__ = (
        CheckConstraint(
            "role IN ('ADMIN', 'TEACHER', 'STUDENT')",
            name="ck_institution_membership_requests_role",
        ),
        CheckConstraint(
            "(request_type = 'JOIN' AND status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'CANCELLED')) "
            "OR (request_type = 'INVITATION' AND status IN ('INVITED', 'ACCEPTED', 'REJECTED', 'CANCELLED'))",
            name="ck_institution_membership_requests_state",
        ),
        Index(
            "ix_institution_membership_requests_institution_status_created",
            "institution_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_institution_membership_requests_user_status_created",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "uq_institution_membership_requests_open_user",
            "institution_id",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('REQUESTED', 'INVITED')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    request_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )