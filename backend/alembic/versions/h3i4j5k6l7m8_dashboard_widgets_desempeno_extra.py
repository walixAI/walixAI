"""dashboard_widgets: 4 widgets extra del panel Desempeño (is_mandatory=false)

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-08-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "h3i4j5k6l7m8"
down_revision = "g2h3i4j5k6l7"
branch_labels = None
depends_on = None

_WIDGETS = [
    ("sales_funnel_chart",    "Embudo de conversión",   3),
    ("lead_sources_chart",    "Fuentes de leads",        4),
    ("lost_deals_chart",      "Razones de pérdida",      5),
    ("team_activity_heatmap", "Actividad del equipo",    6),
]


def upgrade() -> None:
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
                "is_mandatory": False,
                "default_position": pos,
                "surface": "desempeno",
                "is_active": True,
            }
            for key, name, pos in _WIDGETS
        ],
    )


def downgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM dashboard_widgets WHERE key IN "
        "('sales_funnel_chart','lead_sources_chart','lost_deals_chart','team_activity_heatmap')"
    ))
