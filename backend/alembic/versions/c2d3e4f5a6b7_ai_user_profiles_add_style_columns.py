"""ai_user_profiles: add communication_style + preferred_message_length (Etapa 7.5.0)

Revision ID: c2d3e4f5a6b7
Revises: f9a0b1c2d3e4
Create Date: 2026-07-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_user_profiles", sa.Column("communication_style", sa.String(20), nullable=True))
    op.add_column("ai_user_profiles", sa.Column("preferred_message_length", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_user_profiles", "preferred_message_length")
    op.drop_column("ai_user_profiles", "communication_style")
