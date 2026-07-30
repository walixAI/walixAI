"""Metas/Finanzas schema: tenant + branch goals, deal_type, finance_permissions (Metas feature)

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tenants: 4 new columns ────────────────────────────────────────────────
    op.add_column("tenants", sa.Column(
        "deal_type_options", postgresql.JSONB(), nullable=False,
        server_default='["Venta", "Servicio"]',
    ))
    op.add_column("tenants", sa.Column(
        "finance_scope", sa.String(10), nullable=False, server_default="branch",
    ))
    op.add_column("tenants", sa.Column(
        "monthly_goal_total", sa.Numeric(14, 2), nullable=False, server_default="0",
    ))
    op.add_column("tenants", sa.Column(
        "monthly_goal_by_type", postgresql.JSONB(), nullable=False, server_default="{}",
    ))

    # ── branches: 2 new columns ───────────────────────────────────────────────
    op.add_column("branches", sa.Column(
        "monthly_goal_total", sa.Numeric(14, 2), nullable=False, server_default="0",
    ))
    op.add_column("branches", sa.Column(
        "monthly_goal_by_type", postgresql.JSONB(), nullable=False, server_default="{}",
    ))

    # ── deals: 1 new column ───────────────────────────────────────────────────
    op.add_column("deals", sa.Column("deal_type", sa.String(50), nullable=True))

    # ── finance_permissions: new table ────────────────────────────────────────
    op.create_table(
        "finance_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "tenant_id", "branch_id", "user_id",
            name="uq_finance_permissions_tenant_branch_user",
        ),
    )
    op.create_index("ix_finance_permissions_tenant_id", "finance_permissions", ["tenant_id"])
    op.create_index("ix_finance_permissions_branch_id", "finance_permissions", ["branch_id"])
    op.create_index("ix_finance_permissions_user_id", "finance_permissions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_finance_permissions_user_id", table_name="finance_permissions")
    op.drop_index("ix_finance_permissions_branch_id", table_name="finance_permissions")
    op.drop_index("ix_finance_permissions_tenant_id", table_name="finance_permissions")
    op.drop_table("finance_permissions")

    op.drop_column("deals", "deal_type")

    op.drop_column("branches", "monthly_goal_by_type")
    op.drop_column("branches", "monthly_goal_total")

    op.drop_column("tenants", "monthly_goal_by_type")
    op.drop_column("tenants", "monthly_goal_total")
    op.drop_column("tenants", "finance_scope")
    op.drop_column("tenants", "deal_type_options")
