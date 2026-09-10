import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .comment import Comment
    from .post import Post
    from .user import User


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "type IN ('LIKE', 'COMMENT', 'FOLLOW', 'MESSAGE')",
            name="ck_notifications_type",
        ),
        Index("ix_notifications_recipient_created_at", "recipient_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    post_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("posts.id", ondelete="SET NULL"),
        nullable=True,
    )
    comment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("comments.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    recipient: Mapped["User"] = relationship(foreign_keys=[recipient_id])
    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_id])
    post: Mapped["Post | None"] = relationship(foreign_keys=[post_id])
    comment: Mapped["Comment | None"] = relationship(foreign_keys=[comment_id])
