"""Add user-uploaded music and playlists.

Revision ID: 0028_music_library
Revises: 0027_video_library
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0028_music_library"
down_revision: Union[str, None] = "0027_video_library"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("artist_name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(12), nullable=False, server_default="PUBLIC"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("play_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rights_confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("visibility IN ('PUBLIC', 'FOLLOWERS', 'PRIVATE')", name="ck_tracks_visibility"),
        sa.CheckConstraint("play_count >= 0", name="ck_tracks_play_count"),
    )
    op.create_index("ix_tracks_category_created", "tracks", ["category", "created_at"])
    op.create_index("ix_tracks_owner_created", "tracks", ["owner_id", "created_at"])
    op.create_table(
        "playlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("visibility", sa.String(12), nullable=False, server_default="PUBLIC"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("visibility IN ('PUBLIC', 'FOLLOWERS', 'PRIVATE')", name="ck_playlists_visibility"),
    )
    op.create_index("ix_playlists_owner_created", "playlists", ["owner_id", "created_at"])
    op.create_table(
        "playlist_items",
        sa.Column("playlist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("playlist_id", "position", name="uq_playlist_items_position"),
    )
    op.create_table(
        "music_category_follows",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("category", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("music_category_follows")
    op.drop_table("playlist_items")
    op.drop_index("ix_playlists_owner_created", table_name="playlists")
    op.drop_table("playlists")
    op.drop_index("ix_tracks_owner_created", table_name="tracks")
    op.drop_index("ix_tracks_category_created", table_name="tracks")
    op.drop_table("tracks")
