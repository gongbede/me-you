import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .user import User


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint("length(btrim(content)) > 0", name="ck_posts_content_not_blank"),
        CheckConstraint(
            "visibility IN ('PUBLIC', 'AUTHENTICATED', 'NETWORK', 'PRIVATE')",
            name="ck_posts_visibility",
        ),
        Index("ix_posts_author_created_at", "author_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PUBLIC", server_default="PUBLIC"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    author: Mapped["User"] = relationship()
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post", cascade="all, delete-orphan", passive_deletes=True
    )
    likes: Mapped[list["PostLike"]] = relationship(
        back_populates="post", cascade="all, delete-orphan", passive_deletes=True
    )


if TYPE_CHECKING:
    from .comment import Comment
    from .post_like import PostLike
