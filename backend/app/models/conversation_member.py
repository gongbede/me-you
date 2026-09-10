import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .conversation import Conversation
    from .user import User


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    __table_args__ = (Index("ix_conversation_members_user_id", "user_id"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()
