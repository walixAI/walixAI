"""dashboard_widgets: sembrar 3 widgets del panel Desempeño

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g2h3i4j5k6l7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

_WIDGETS = [
    ("team_performance_summary", "Rendimiento del equipo",         True,  0),
    ("ai_roi_summary",           "Impacto del copiloto IA (ROI)",  True,  1),
    ("lead_quality_forecast",    "Forecast de calidad de leads",   True,  2),
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
                "is_mandatory": is_mandatory,
                "default_position": pos,
                "surface": "desempeno",
                "is_active": True,
            }
            for key, name, is_mandatory, pos in _WIDGETS
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM dashboard_widgets WHERE key IN ('team_performance_summary', 'ai_roi_summary', 'lead_quality_forecast')")
    )
