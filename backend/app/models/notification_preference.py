import uuid

from sqlalchemy import Boolean, ForeignKey, String, Uuid, true
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    notification_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
