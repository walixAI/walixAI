"""Metas Gen2: tenant.count_business_days + tenant.profit_thresholds

Revision ID: h5i6j7k8l9m0
Revises: g6b7c8d9e0f1
Create Date: 2026-07-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "h5i6j7k8l9m0"
down_revision = "g6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column(
        "count_business_days", sa.Boolean(), nullable=False, server_default="true",
    ))
    op.add_column("tenants", sa.Column(
        "profit_thresholds",
        postgresql.JSONB(),
        nullable=False,
        server_default='{"green": 20, "yellow": 10, "orange": 0}',
    ))


def downgrade() -> None:
    op.drop_column("tenants", "profit_thresholds")
    op.drop_column("tenants", "count_business_days")
