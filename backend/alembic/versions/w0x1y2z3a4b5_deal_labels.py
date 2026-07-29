"""Deal labels: deal_name y deal_plural en tenants.

Revision ID: w0x1y2z3a4b5
Revises: v9w0x1y2z3a4
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op

revision = "w0x1y2z3a4b5"
down_revision = "v9w0x1y2z3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("deal_name", sa.String(50), nullable=False, server_default="Oportunidad"),
    )
    op.add_column(
        "tenants",
        sa.Column("deal_plural", sa.String(50), nullable=False, server_default="Oportunidades"),
    )


def downgrade() -> None:
    op.drop_column("tenants", "deal_plural")
    op.drop_column("tenants", "deal_name")
