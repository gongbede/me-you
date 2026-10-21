import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .media_asset import MediaAsset
    from .post import Post


class PostAttachment(Base):
    __tablename__ = "post_attachments"
    __table_args__ = (
        CheckConstraint("position BETWEEN 0 AND 3", name="ck_post_attachments_position"),
        UniqueConstraint("post_id", "position", name="uq_post_attachments_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    media_asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    alt_text: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    post: Mapped["Post"] = relationship(back_populates="attachments")
    media_asset: Mapped["MediaAsset"] = relationship()