"""B1: copilot_capabilities + copilot_action_log — schema del Walix Builder

Tabla copilot_capabilities:
  Recetas de hasta N pasos encadenando primitivas del Copiloto. Soporta
  scope (all/role/user), canal, confirmación obligatoria, límite diario.
  Diseñada para soportar ejecución dinámica real (motor B3) — no solo almacenamiento.

Tabla copilot_action_log:
  Bitácora inmutable de cada paso ejecutado (ok/error/dry_run).
  updated_at incluida explícitamente — Base la exige en todo modelo
  aunque la tabla sea append-only.

Decisiones de schema:
  - trigger_phrases / scope_roles / scope_user_ids / channels → JSONB
    (el proyecto no usa postgresql.ARRAY en ningún modelo; JSONB es el
    patrón universal para listas: key_facts, tool_calls, form_ids, etc.)
  - kind CHECK en Postgres: mismo patrón que otros string enums en el proyecto
  - scope_roles guarda valores del UserRole real de walixAI en minúsculas
    (ej. "owner", "gerente", "asesor") — NO los nombres de Lovable

Revision ID: k8l9m0n1o2p3
Revises: j7k8l9m0n1o2
Create Date: 2026-07-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "k8l9m0n1o2p3"
down_revision = "j7k8l9m0n1o2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── copilot_capabilities ──────────────────────────────────────────────────
    op.create_table(
        "copilot_capabilities",
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
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # "recipe" = pasos encadenados definidos en recipe_json
        # "native" = reservado para primitivas built-in del motor
        sa.Column(
            "kind",
            sa.String(20),
            nullable=False,
            server_default="recipe",
        ),
        sa.Column(
            "recipe_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # Frases que pueden disparar esta receta (lista de strings en JSONB)
        sa.Column(
            "trigger_phrases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # "all" | "role" | "user"
        sa.Column(
            "scope_type",
            sa.String(10),
            nullable=False,
            server_default="all",
        ),
        # Valores del UserRole real de walixAI en minúsculas: "gerente", "asesor", etc.
        sa.Column(
            "scope_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # UUIDs de usuarios específicos con acceso
        sa.Column(
            "scope_user_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # Canales donde está disponible la receta: ["web"] | ["whatsapp"] | ["web","whatsapp"]
        sa.Column(
            "channels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"web\"]'::jsonb"),
        ),
        sa.Column(
            "require_confirmation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("kind IN ('recipe', 'native')", name="ck_copilot_cap_kind"),
        sa.CheckConstraint("scope_type IN ('all', 'role', 'user')", name="ck_copilot_cap_scope_type"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_copilot_capabilities_tenant_active",
        "copilot_capabilities",
        ["tenant_id", "is_active"],
    )
    op.create_index(
        "ix_copilot_capabilities_tenant_id",
        "copilot_capabilities",
        ["tenant_id"],
    )

    # ── copilot_action_log ────────────────────────────────────────────────────
    op.create_table(
        "copilot_action_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # updated_at incluida aunque la tabla sea append-only:
        # Base la define en todos los modelos y la migración debe ser consistente.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("step_index", sa.Integer(), nullable=True),
        sa.Column("step_name", sa.String(100), nullable=True),
        sa.Column(
            "input",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "output",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # "ok" | "error" | "dry_run"
        sa.Column(
            "status",
            sa.String(10),
            nullable=False,
            server_default="ok",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('ok', 'error', 'dry_run')", name="ck_copilot_log_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["capability_id"], ["copilot_capabilities.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_copilot_action_log_tenant_created",
        "copilot_action_log",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_copilot_action_log_capability_id",
        "copilot_action_log",
        ["capability_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_copilot_action_log_capability_id", table_name="copilot_action_log")
    op.drop_index("ix_copilot_action_log_tenant_created", table_name="copilot_action_log")
    op.drop_table("copilot_action_log")
    op.drop_index("ix_copilot_capabilities_tenant_id", table_name="copilot_capabilities")
    op.drop_index("ix_copilot_capabilities_tenant_active", table_name="copilot_capabilities")
    op.drop_table("copilot_capabilities")
