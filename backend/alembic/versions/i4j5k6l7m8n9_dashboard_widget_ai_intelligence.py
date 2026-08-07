"""dashboard_widgets: ai_intelligence_section en panel principal

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-08-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i4j5k6l7m8n9"
down_revision = "h3i4j5k6l7m8"
branch_labels = None
depends_on = None


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
                "key": "ai_intelligence_section",
                "name": "Inteligencia IA",
                "native_key": "ai_intelligence_section",
                "is_mandatory": False,
                "default_position": 8,
                "surface": "principal",
                "is_active": True,
            }
        ],
    )


def downgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM dashboard_widgets WHERE key = 'ai_intelligence_section'"
    ))
