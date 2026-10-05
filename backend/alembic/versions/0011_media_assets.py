"""Add private provider-backed media asset metadata.

Revision ID: 0011_media_assets
Revises: 0010_conversation_ownership
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0011_media_assets"
down_revision: Union[str, None] = "0010_conversation_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("storage_provider", sa.String(length=40), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('PROFILE_IMAGE', 'POST_MEDIA', 'COURSE_MEDIA', 'REEL', 'MESSAGE_ATTACHMENT')",
            name="ck_media_assets_purpose",
        ),
        sa.CheckConstraint("status IN ('UPLOAD_PENDING', 'READY', 'FAILED')", name="ck_media_assets_status"),
        sa.CheckConstraint("byte_size > 0", name="ck_media_assets_byte_size_positive"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_media_assets_storage_key"),
    )
    op.create_index("ix_media_assets_owner_created", "media_assets", ["owner_id", "created_at"])
    op.create_index("ix_media_assets_status_expires", "media_assets", ["status", "upload_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_media_assets_status_expires", table_name="media_assets")
    op.drop_index("ix_media_assets_owner_created", table_name="media_assets")
    op.drop_table("media_assets")