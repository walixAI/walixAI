"""agent_suggestions: add entity_type + entity_id columns (Etapa 6.3.0)

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-07-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_suggestions",
        sa.Column("entity_type", sa.String(20), nullable=True),
    )
    op.add_column(
        "agent_suggestions",
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_agent_suggestions_entity_type", "agent_suggestions", ["entity_type"])
    op.create_index("ix_agent_suggestions_entity_id",   "agent_suggestions", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_suggestions_entity_id",   table_name="agent_suggestions")
    op.drop_index("ix_agent_suggestions_entity_type", table_name="agent_suggestions")
    op.drop_column("agent_suggestions", "entity_id")
    op.drop_column("agent_suggestions", "entity_type")
