"""ai_user_profiles table (Etapa 6.5.0)

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-07-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_deals_closed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_deals_lost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("close_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("best_close_day", sa.String(20), nullable=True),
        sa.Column("best_close_hour", sa.Integer(), nullable=True),
        sa.Column("top_performing_stage", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_ai_user_profiles_user_id"),
    )
    op.create_index("ix_ai_user_profiles_tenant_id", "ai_user_profiles", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_user_profiles_tenant_id", table_name="ai_user_profiles")
    op.drop_table("ai_user_profiles")
