"""Sprint 12 — Conectar onboarding con config del bot WhatsApp.

Agrega:
  tenants.onboarding_extracted_data  JSONB nullable
  branches.bot_system_prompt         TEXT nullable
  branches.bot_tone                  VARCHAR(50) nullable
  branches.bot_qualification_questions  JSONB nullable
  branches.bot_config_generated_at   TIMESTAMPTZ nullable
  branches.bot_config_updated_at     TIMESTAMPTZ nullable

Revision ID: p2q3r4s5t6u7
Revises: o1p2q3r4s5t6
Create Date: 2026-06-16
"""

import sqlalchemy as sa
from alembic import op

revision = "p2q3r4s5t6u7"
down_revision = "o1p2q3r4s5t6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("onboarding_extracted_data", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    op.add_column("branches", sa.Column("bot_system_prompt", sa.Text(), nullable=True))
    op.add_column("branches", sa.Column("bot_tone", sa.String(50), nullable=True))
    op.add_column(
        "branches",
        sa.Column("bot_qualification_questions", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "branches",
        sa.Column("bot_config_generated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "branches",
        sa.Column("bot_config_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("branches", "bot_config_updated_at")
    op.drop_column("branches", "bot_config_generated_at")
    op.drop_column("branches", "bot_qualification_questions")
    op.drop_column("branches", "bot_tone")
    op.drop_column("branches", "bot_system_prompt")
    op.drop_column("tenants", "onboarding_extracted_data")
