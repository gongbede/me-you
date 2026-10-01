import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .institution_membership import InstitutionMembership
    from .student import Student
    from .teacher import Teacher
    from .profile import Profile


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    profile: Mapped["Profile"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    memberships: Mapped[list["InstitutionMembership"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    teacher_records: Mapped[list["Teacher"]] = relationship(back_populates="user")
    student_records: Mapped[list["Student"]] = relationship(back_populates="user")
