"""dashboard_widgets + dashboard_layouts — configurable widget catalog

Revision ID: 2b3c4d5e6f7g
Revises: 1a2b3c4d5e6f
Create Date: 2026-08-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "2b3c4d5e6f7g"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None

# Seed: 8 widgets taken 1:1 from Dashboard.tsx sections
_SEED_WIDGETS = [
    ("kpi_cards",                    "KPIs principales",                     True,  False, 0),
    ("run_rate_profitability",        "Run Rate y Rentabilidad",              False, False, 1),
    ("task_cards",                   "Mis Tareas",                           False, False, 2),
    ("recent_activity",              "Actividad Reciente",                   False, False, 3),
    ("proactive_briefing",           "Briefing Proactivo IA",                False, False, 4),
    ("ai_patterns",                  "Patrones de IA",                       False, False, 5),
    ("pipeline_by_stage_chart",      "Pipeline por Etapa",                   False, False, 6),
    ("deals_closed_timeline_chart",  "Oportunidades Cerradas (30 días)",     False, False, 7),
]
# columns: key, name, is_mandatory, has_min_role, default_position


def upgrade() -> None:
    op.create_table(
        "dashboard_widgets",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("native_key", sa.String(100), nullable=False),
        sa.Column("min_role", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("surface", sa.String(50), nullable=False, server_default="dashboard"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_dashboard_widgets_key"),
    )
    op.create_index("ix_dashboard_widgets_key", "dashboard_widgets", ["key"])

    op.create_table(
        "dashboard_layouts",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "scope", name="uq_dashboard_layouts_tenant_scope"),
    )
    op.create_index("ix_dashboard_layouts_tenant_id", "dashboard_layouts", ["tenant_id"])

    # Seed the widget catalog
    widgets_table = sa.table(
        "dashboard_widgets",
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("native_key", sa.String),
        sa.column("is_mandatory", sa.Boolean),
        sa.column("default_position", sa.Integer),
        sa.column("surface", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        widgets_table,
        [
            {
                "key": key,
                "name": name,
                "native_key": key,
                "is_mandatory": is_mandatory,
                "default_position": pos,
                "surface": "dashboard",
                "is_active": True,
            }
            for key, name, is_mandatory, _has_min_role, pos in _SEED_WIDGETS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_dashboard_layouts_tenant_id", table_name="dashboard_layouts")
    op.drop_table("dashboard_layouts")
    op.drop_index("ix_dashboard_widgets_key", table_name="dashboard_widgets")
    op.drop_table("dashboard_widgets")
