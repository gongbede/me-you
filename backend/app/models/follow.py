import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .user import User


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (
        CheckConstraint("follower_id <> following_id", name="ck_follows_not_self"),
        Index("ix_follows_following_id", "following_id"),
    )

    follower_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    following_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    follower: Mapped["User"] = relationship(foreign_keys=[follower_id])
    following: Mapped["User"] = relationship(foreign_keys=[following_id])
