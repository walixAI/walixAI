"""Sprint 8B — Industry Templates: nuevas columnas en tenants y pipeline_stages,
tabla onboarding_conversations.

Revision ID: k7l8m9n0o1p2
Revises: j6k7l8m9n0o1
Create Date: 2026-06-14
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "k7l8m9n0o1p2"
down_revision = "j6k7l8m9n0o1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Nuevas columnas en `tenants` ───────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column("industry_key", sa.String(50), nullable=False, server_default="generico"),
    )
    op.add_column(
        "tenants",
        sa.Column("industry_label", sa.String(100), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("entity_name", sa.String(50), nullable=False, server_default="Contacto"),
    )
    op.add_column(
        "tenants",
        sa.Column("entity_plural", sa.String(50), nullable=False, server_default="Contactos"),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "contact_statuses_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "tenants",
        sa.Column("onboarding_description", sa.Text(), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── 2. Nuevas columnas en `pipeline_stages` ───────────────────────────────
    op.add_column(
        "pipeline_stages",
        sa.Column("stage_key", sa.String(50), nullable=True),
    )
    # color ya existe como nullable — la volvemos NOT NULL con default
    op.alter_column(
        "pipeline_stages",
        "color",
        existing_type=sa.String(7),
        nullable=False,
        server_default="#6B7280",
    )
    op.add_column(
        "pipeline_stages",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Índice parcial único: (tenant_id, stage_key) WHERE is_archived = false
    op.create_index(
        "uq_pipeline_stage_key",
        "pipeline_stages",
        ["tenant_id", "stage_key"],
        unique=True,
        postgresql_where=sa.text("is_archived = false AND stage_key IS NOT NULL"),
    )

    # ── 3. Nueva tabla `onboarding_conversations` ─────────────────────────────
    op.create_table(
        "onboarding_conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn", sa.SmallInteger(), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column(
            "extracted_data",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("inferred_industry", sa.String(50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "follow_up_questions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
    )
    op.create_index(
        "ix_onboarding_conversations_tenant_session_turn",
        "onboarding_conversations",
        ["tenant_id", "session_id", "turn"],
    )


def downgrade() -> None:
    # ── 3. Eliminar tabla onboarding_conversations ────────────────────────────
    op.drop_index(
        "ix_onboarding_conversations_tenant_session_turn",
        table_name="onboarding_conversations",
    )
    op.drop_table("onboarding_conversations")

    # ── 2. Revertir columnas de pipeline_stages ───────────────────────────────
    op.drop_index("uq_pipeline_stage_key", table_name="pipeline_stages")
    op.drop_column("pipeline_stages", "is_archived")
    op.alter_column(
        "pipeline_stages",
        "color",
        existing_type=sa.String(7),
        nullable=True,
        server_default=None,
    )
    op.drop_column("pipeline_stages", "stage_key")

    # ── 1. Revertir columnas de tenants ───────────────────────────────────────
    op.drop_column("tenants", "onboarding_completed_at")
    op.drop_column("tenants", "onboarding_description")
    op.drop_column("tenants", "contact_statuses_config")
    op.drop_column("tenants", "entity_plural")
    op.drop_column("tenants", "entity_name")
    op.drop_column("tenants", "industry_label")
    op.drop_column("tenants", "industry_key")
