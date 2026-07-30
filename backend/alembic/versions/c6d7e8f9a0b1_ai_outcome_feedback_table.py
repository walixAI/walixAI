"""ai_outcome_feedback table (Etapa 6.3.3)

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-07-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_outcome_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suggestion_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_taken", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=True),
        sa.Column("outcome_value", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("days_to_outcome", sa.Integer(), nullable=True),
        sa.Column("context_at_action", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suggestion_id"], ["agent_suggestions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_outcome_feedback_tenant_id",      "ai_outcome_feedback", ["tenant_id"])
    op.create_index("ix_ai_outcome_feedback_suggestion_id",  "ai_outcome_feedback", ["suggestion_id"])
    op.create_index("ix_ai_outcome_feedback_entity_type",    "ai_outcome_feedback", ["entity_type"])
    op.create_index("ix_ai_outcome_feedback_entity_id",      "ai_outcome_feedback", ["entity_id"])
    op.create_index("ix_ai_outcome_feedback_tenant_created", "ai_outcome_feedback", ["tenant_id", "created_at"])
    op.create_index("ix_ai_outcome_feedback_tenant_outcome", "ai_outcome_feedback", ["tenant_id", "outcome"])


def downgrade() -> None:
    op.drop_index("ix_ai_outcome_feedback_tenant_outcome", table_name="ai_outcome_feedback")
    op.drop_index("ix_ai_outcome_feedback_tenant_created", table_name="ai_outcome_feedback")
    op.drop_index("ix_ai_outcome_feedback_entity_id",      table_name="ai_outcome_feedback")
    op.drop_index("ix_ai_outcome_feedback_entity_type",    table_name="ai_outcome_feedback")
    op.drop_index("ix_ai_outcome_feedback_suggestion_id",  table_name="ai_outcome_feedback")
    op.drop_index("ix_ai_outcome_feedback_tenant_id",      table_name="ai_outcome_feedback")
    op.drop_table("ai_outcome_feedback")
