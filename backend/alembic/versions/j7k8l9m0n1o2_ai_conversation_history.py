"""C1: ai_conversation_history — schema para historial del Copiloto conversacional

Tabla: ai_conversation_history
- id, created_at, updated_at (heredados de Base — CRÍTICO: incluir updated_at explícitamente)
- tenant_id, user_id (FK con CASCADE)
- session_id String(100): equivalente al conversationKey del frontend ("global", "contact:uuid", …)
- role String(10): user/assistant/tool (validación en Pydantic, sin CHECK de DB)
- content Text
- tool_calls JSONB default []
- context_snapshot JSONB default {}

Índices:
- (session_id, created_at) compuesto — lecturas de historial por sesión ordenadas
- tenant_id simple
- user_id simple

Revision ID: j7k8l9m0n1o2
Revises: i6j7k8l9m0n1
Create Date: 2026-07-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "j7k8l9m0n1o2"
down_revision = "i6j7k8l9m0n1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_conversation_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tool_calls",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "context_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_conv_history_session_created",
        "ai_conversation_history",
        ["session_id", "created_at"],
    )
    op.create_index(
        "ix_ai_conv_history_tenant_id",
        "ai_conversation_history",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ai_conv_history_user_id",
        "ai_conversation_history",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_conv_history_user_id", table_name="ai_conversation_history")
    op.drop_index("ix_ai_conv_history_tenant_id", table_name="ai_conversation_history")
    op.drop_index("ix_ai_conv_history_session_created", table_name="ai_conversation_history")
    op.drop_table("ai_conversation_history")
