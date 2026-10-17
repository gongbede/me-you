import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        CheckConstraint("visibility IN ('PUBLIC', 'FOLLOWERS', 'PRIVATE')", name="ck_tracks_visibility"),
        CheckConstraint("play_count >= 0", name="ck_tracks_play_count"),
        Index("ix_tracks_category_created", "category", "created_at"),
        Index("ix_tracks_owner_created", "owner_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    media_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("media_assets.id", ondelete="RESTRICT"), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    artist_name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    visibility: Mapped[str] = mapped_column(String(12), nullable=False, default="PUBLIC")
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rights_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Playlist(Base):
    __tablename__ = "playlists"
    __table_args__ = (
        CheckConstraint("visibility IN ('PUBLIC', 'FOLLOWERS', 'PRIVATE')", name="ck_playlists_visibility"),
        Index("ix_playlists_owner_created", "owner_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    visibility: Mapped[str] = mapped_column(String(12), nullable=False, default="PUBLIC")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class PlaylistItem(Base):
    __tablename__ = "playlist_items"
    __table_args__ = (UniqueConstraint("playlist_id", "position", name="uq_playlist_items_position"),)
    playlist_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True)
    track_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class MusicCategoryFollow(Base):
    __tablename__ = "music_category_follows"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
