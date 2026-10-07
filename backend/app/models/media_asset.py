import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

if TYPE_CHECKING:
    from .user import User


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('PROFILE_IMAGE', 'POST_MEDIA', 'COURSE_MEDIA', 'REEL', 'MESSAGE_ATTACHMENT')",
            name="ck_media_assets_purpose",
        ),
        CheckConstraint(
            "status IN ('UPLOAD_PENDING', 'READY', 'FAILED')",
            name="ck_media_assets_status",
        ),
        CheckConstraint("byte_size > 0", name="ck_media_assets_byte_size_positive"),
        UniqueConstraint("storage_key", name="uq_media_assets_storage_key"),
        Index("ix_media_assets_owner_created", "owner_id", "created_at"),
        Index("ix_media_assets_status_expires", "status", "upload_expires_at"),
        Index("ix_media_assets_institution_status", "institution_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UPLOAD_PENDING")
    storage_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upload_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )