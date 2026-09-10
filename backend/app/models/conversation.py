import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .conversation_member import ConversationMember
    from .message import Message


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("type IN ('DIRECT', 'GROUP')", name="ck_conversations_type"),
        CheckConstraint(
            "type = 'GROUP' OR direct_key IS NOT NULL",
            name="ck_conversations_direct_key",
        ),
        Index("ix_conversations_updated_at", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    direct_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    members: Mapped[list["ConversationMember"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True)
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True)
