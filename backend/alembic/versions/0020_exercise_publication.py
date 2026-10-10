"""Add exercise publication state.

Revision ID: 0020_exercise_publication
Revises: 0019_phone_login_codes
Create Date: 2026-10-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020_exercise_publication"
down_revision: Union[str, None] = "0019_phone_login_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "exercises",
        sa.Column("is_published", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.alter_column(
        "exercises",
        "is_published",
        existing_type=sa.Boolean(),
        server_default=sa.false(),
    )


def downgrade() -> None:
    op.drop_column("exercises", "is_published")