import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class PhoneLoginCode(Base):
    __tablename__ = "phone_login_codes"
    __table_args__ = (
        CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_phone_login_codes_attempts"),
        UniqueConstraint("phone_number", name="uq_phone_login_codes_phone_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)