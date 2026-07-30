"""Metas/Gastos paridad Lovable: recurring_expenses, expense_rules, expense/deal columns

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. recurring_expenses (must exist before expenses.recurring_id FK) ────
    op.create_table(
        "recurring_expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["expense_categories.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_recurring_expenses_tenant", "recurring_expenses", ["tenant_id"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ── 2. expense_rules (must exist before expenses.rule_id FK) ─────────────
    op.create_table(
        "expense_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rule_type", sa.String(20), nullable=False),
        sa.Column("value", sa.Numeric(10, 2), nullable=False),
        sa.Column("deal_type_filter", sa.String(20), nullable=True),
        sa.Column("auto_confirm", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["expense_categories.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_expense_rules_tenant", "expense_rules", ["tenant_id"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ── 3. expense_categories: new column ────────────────────────────────────
    op.add_column("expense_categories", sa.Column("icon", sa.String(50), nullable=True))

    # ── 4. expenses: new columns + FKs to tables created above ───────────────
    op.add_column("expenses", sa.Column(
        "currency", sa.String(3), nullable=False, server_default="MXN",
    ))
    op.add_column("expenses", sa.Column("receipt_url", sa.Text(), nullable=True))
    op.add_column("expenses", sa.Column(
        "status", sa.String(10), nullable=False, server_default="confirmed",
    ))
    op.add_column("expenses", sa.Column(
        "source", sa.String(10), nullable=False, server_default="manual",
    ))
    op.add_column("expenses", sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("expenses", sa.Column("recurring_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_expenses_rule_id", "expenses", "expense_rules", ["rule_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_expenses_recurring_id", "expenses", "recurring_expenses", ["recurring_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_expenses_status", "expenses", ["tenant_id", "status"])
    op.create_index("ix_expenses_recurring", "expenses", ["recurring_id", "incurred_at"])

    # ── 5. deals: cost_amount ─────────────────────────────────────────────────
    op.add_column("deals", sa.Column(
        "cost_amount", sa.Numeric(14, 2), nullable=False, server_default="0",
    ))


def downgrade() -> None:
    # ── 5. deals ──────────────────────────────────────────────────────────────
    op.drop_column("deals", "cost_amount")

    # ── 4. expenses ───────────────────────────────────────────────────────────
    op.drop_index("ix_expenses_recurring", table_name="expenses")
    op.drop_index("ix_expenses_status", table_name="expenses")
    op.drop_constraint("fk_expenses_recurring_id", "expenses", type_="foreignkey")
    op.drop_constraint("fk_expenses_rule_id", "expenses", type_="foreignkey")
    op.drop_column("expenses", "recurring_id")
    op.drop_column("expenses", "rule_id")
    op.drop_column("expenses", "source")
    op.drop_column("expenses", "status")
    op.drop_column("expenses", "receipt_url")
    op.drop_column("expenses", "currency")

    # ── 3. expense_categories ─────────────────────────────────────────────────
    op.drop_column("expense_categories", "icon")

    # ── 2. expense_rules ──────────────────────────────────────────────────────
    op.drop_index("ix_expense_rules_tenant", table_name="expense_rules")
    op.drop_table("expense_rules")

    # ── 1. recurring_expenses ─────────────────────────────────────────────────
    op.drop_index("ix_recurring_expenses_tenant", table_name="recurring_expenses")
    op.drop_table("recurring_expenses")
