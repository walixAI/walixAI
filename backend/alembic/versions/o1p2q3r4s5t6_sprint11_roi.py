"""Sprint 11 — ROI dashboard: roi_revenue_per_conversion on tenants.

Revision ID: o1p2q3r4s5t6
Revises: n0o1p2q3r4s5
Create Date: 2026-06-15
"""

import sqlalchemy as sa
from alembic import op

revision = "o1p2q3r4s5t6"
down_revision = "n0o1p2q3r4s5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "roi_revenue_per_conversion",
            sa.Numeric(10, 2),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "roi_revenue_per_conversion")
