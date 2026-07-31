"""Metas Gen2: product_categories, monthly_goals, assignments, history + deal.product_category_id

Revision ID: g6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-07-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "g6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. product_categories ─────────────────────────────────────────────────
    op.create_table(
        "product_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_product_categories_tenant_name"),
    )
    op.create_index("ix_product_categories_tenant_id", "product_categories", ["tenant_id"])

    # ── 2. deals: product_category_id ─────────────────────────────────────────
    op.add_column("deals", sa.Column("product_category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_deals_product_category_id",
        "deals", "product_categories",
        ["product_category_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_deals_product_category_id", "deals", ["product_category_id"])

    # ── 3. monthly_goals ──────────────────────────────────────────────────────
    op.create_table(
        "monthly_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="MXN"),
        sa.Column("dimension", sa.String(20), nullable=False),
        sa.Column("dimension_value_text", sa.String(50), nullable=True),
        sa.Column("dimension_value_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_monthly_goals_tenant_id", "monthly_goals", ["tenant_id"])
    # Unique on all 6 dimension columns. NULL values are not equal in Postgres unique
    # indexes, so uniqueness for NULL dimensions is enforced at the application layer.
    op.create_index(
        "ix_monthly_goals_tenant_period_dimension",
        "monthly_goals",
        ["tenant_id", "period_year", "period_month", "dimension",
         "dimension_value_text", "dimension_value_uuid"],
        unique=True,
    )

    # ── 4. monthly_goal_assignments ───────────────────────────────────────────
    op.create_table(
        "monthly_goal_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("share_percent", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["goal_id"], ["monthly_goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("goal_id", "user_id", name="uq_monthly_goal_assignments_goal_user"),
    )
    op.create_index("ix_monthly_goal_assignments_goal_id", "monthly_goal_assignments", ["goal_id"])
    op.create_index("ix_monthly_goal_assignments_tenant_id", "monthly_goal_assignments", ["tenant_id"])
    op.create_index("ix_monthly_goal_assignments_user_id", "monthly_goal_assignments", ["user_id"])

    # ── 5. monthly_goal_history ───────────────────────────────────────────────
    # goal_id and changed_by are stored without FK so history survives deletions.
    op.create_table(
        "monthly_goal_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("before_data", postgresql.JSONB(), nullable=True),
        sa.Column("after_data", postgresql.JSONB(), nullable=True),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_monthly_goal_history_tenant_id", "monthly_goal_history", ["tenant_id"])
    op.create_index("ix_monthly_goal_history_goal_id", "monthly_goal_history", ["goal_id"])


def downgrade() -> None:
    op.drop_index("ix_monthly_goal_history_goal_id", table_name="monthly_goal_history")
    op.drop_index("ix_monthly_goal_history_tenant_id", table_name="monthly_goal_history")
    op.drop_table("monthly_goal_history")

    op.drop_index("ix_monthly_goal_assignments_user_id", table_name="monthly_goal_assignments")
    op.drop_index("ix_monthly_goal_assignments_tenant_id", table_name="monthly_goal_assignments")
    op.drop_index("ix_monthly_goal_assignments_goal_id", table_name="monthly_goal_assignments")
    op.drop_table("monthly_goal_assignments")

    op.drop_index("ix_monthly_goals_tenant_period_dimension", table_name="monthly_goals")
    op.drop_index("ix_monthly_goals_tenant_id", table_name="monthly_goals")
    op.drop_table("monthly_goals")

    op.drop_index("ix_deals_product_category_id", table_name="deals")
    op.drop_constraint("fk_deals_product_category_id", "deals", type_="foreignkey")
    op.drop_column("deals", "product_category_id")

    op.drop_index("ix_product_categories_tenant_id", table_name="product_categories")
    op.drop_table("product_categories")
