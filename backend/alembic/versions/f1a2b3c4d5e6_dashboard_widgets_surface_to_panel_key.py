"""dashboard_widgets: surface 'dashboard' → 'principal' para alinear con panel_key

Revision ID: f1a2b3c4d5e6
Revises: e40231c281ca
Create Date: 2026-08-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e40231c281ca"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE dashboard_widgets SET surface = 'principal' WHERE surface = 'dashboard'"))


def downgrade() -> None:
    op.execute(sa.text("UPDATE dashboard_widgets SET surface = 'dashboard' WHERE surface = 'principal'"))
