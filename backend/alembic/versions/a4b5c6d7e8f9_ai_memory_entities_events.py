"""ai_entity_context and ai_memory_events tables (Etapa 6.1)

Revision ID: a4b5c6d7e8f9
Revises: z3a4b5c6d7e8
Create Date: 2026-07-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a4b5c6d7e8f9"
down_revision = "z3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_entity_context",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("key_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("last_interaction", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sentiment", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("urgency_score", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "tenant_id", "entity_type", "entity_id",
            name="uq_ai_entity_context_tenant_type_entity",
        ),
    )
    op.create_index("ix_ai_entity_context_tenant_id",   "ai_entity_context", ["tenant_id"])
    op.create_index("ix_ai_entity_context_branch_id",   "ai_entity_context", ["branch_id"])
    op.create_index("ix_ai_entity_context_entity_type", "ai_entity_context", ["entity_type"])
    op.create_index("ix_ai_entity_context_entity_id",   "ai_entity_context", ["entity_id"])

    op.create_table(
        "ai_memory_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_memory_events_tenant_id",             "ai_memory_events", ["tenant_id"])
    op.create_index("ix_ai_memory_events_entity_type",           "ai_memory_events", ["entity_type"])
    op.create_index("ix_ai_memory_events_entity_id",             "ai_memory_events", ["entity_id"])
    op.create_index(
        "ix_ai_memory_events_tenant_entity_created",
        "ai_memory_events",
        ["tenant_id", "entity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_memory_events_tenant_entity_created", table_name="ai_memory_events")
    op.drop_index("ix_ai_memory_events_entity_id",             table_name="ai_memory_events")
    op.drop_index("ix_ai_memory_events_entity_type",           table_name="ai_memory_events")
    op.drop_index("ix_ai_memory_events_tenant_id",             table_name="ai_memory_events")
    op.drop_table("ai_memory_events")

    op.drop_index("ix_ai_entity_context_entity_id",   table_name="ai_entity_context")
    op.drop_index("ix_ai_entity_context_entity_type", table_name="ai_entity_context")
    op.drop_index("ix_ai_entity_context_branch_id",   table_name="ai_entity_context")
    op.drop_index("ix_ai_entity_context_tenant_id",   table_name="ai_entity_context")
    op.drop_table("ai_entity_context")
