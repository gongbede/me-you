import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AccountEmailToken(Base):
    __tablename__ = "account_email_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET')",
            name="ck_account_email_tokens_purpose",
        ),
        UniqueConstraint("token_hash", name="uq_account_email_tokens_hash"),
        Index("ix_account_email_tokens_user_purpose", "user_id", "purpose", "consumed_at"),
        Index("ix_account_email_tokens_expiry", "expires_at"),
        Index(
            "uq_account_email_tokens_active_user_purpose",
            "user_id",
            "purpose",
            unique=True,
            postgresql_where=text("consumed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )