"""platform_ai_model_config — Copiloto Fase 1, Parte B.

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-08-18

Tabla RAÍZ, igual que tenants/companies — SIN tenant_id y SIN RLS a
propósito: no pertenece a ningún tenant, es una decisión de plataforma
completa. Solo el platform_owner debe poder escribirla, y eso se aplica a
nivel de aplicación (en el endpoint de Fase 7, no acá) — no vía RLS, que
no tendría sentido en una tabla sin tenant_id.

Sembrada con los valores default reales que el código ya usa hoy:
  - tier='simple'   -> claude-haiku-4-5-20251001 (app/ai/copilot_engine.py,
    app/api/ai.py, etc.)
  - tier='compleja' -> claude-sonnet-4-6 (app/agents/closing_agent.py,
    app/api/onboarding.py)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r3s4t5u6v7w8"
down_revision = "q2r3s4t5u6v7"
branch_labels = None
depends_on = None

_SEED = [
    ("simple", "claude-haiku-4-5-20251001"),
    ("compleja", "claude-sonnet-4-6"),
]


def upgrade() -> None:
    op.create_table(
        "platform_ai_model_config",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tier", name="uq_platform_ai_model_config_tier"),
    )

    config_table = sa.table(
        "platform_ai_model_config",
        sa.column("tier", sa.String),
        sa.column("model_name", sa.String),
    )
    op.bulk_insert(config_table, [{"tier": tier, "model_name": model} for tier, model in _SEED])


def downgrade() -> None:
    op.drop_table("platform_ai_model_config")
