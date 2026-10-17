import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('POST', 'COMMENT', 'REEL', 'USER', 'MESSAGE')",
            name="ck_reports_target_type",
        ),
        CheckConstraint(
            "reason IN ('SPAM', 'HARASSMENT', 'INAPPROPRIATE', 'MISINFORMATION', 'OTHER')",
            name="ck_reports_reason",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'REVIEWED', 'DISMISSED', 'ACTIONED')",
            name="ck_reports_status",
        ),
        Index("ix_reports_status_created_at", "status", "created_at"),
        Index("ix_reports_target", "target_type", "target_id"),
        Index("uq_reports_open_reporter_target", "reporter_id", "target_type", "target_id",
              unique=True, postgresql_where="status = 'OPEN'"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(8), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="OPEN", server_default="OPEN"
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
