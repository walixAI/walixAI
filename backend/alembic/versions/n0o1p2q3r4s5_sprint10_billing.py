"""Sprint 10 — Stripe billing: subscriptions + failed_payments tables.

Revision ID: n0o1p2q3r4s5
Revises: m9n0o1p2q3r4
Create Date: 2026-06-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "n0o1p2q3r4s5"
down_revision = "m9n0o1p2q3r4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscriptions ─────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stripe_customer_id", sa.String(100), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(100), nullable=True),
        sa.Column("stripe_price_id", sa.String(100), nullable=True),
        sa.Column("plan", sa.String(50), nullable=False, server_default="trial"),
        sa.Column("status", sa.String(50), nullable=False, server_default="trialing"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_subscription_id", name="uq_subscriptions_stripe_sub_id"),
    )
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"])
    op.create_index("ix_subscriptions_stripe_customer_id", "subscriptions", ["stripe_customer_id"])
    op.create_index("ix_subscriptions_stripe_subscription_id", "subscriptions", ["stripe_subscription_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    # ── failed_payments ───────────────────────────────────────────────────────
    op.create_table(
        "failed_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stripe_invoice_id", sa.String(100), nullable=False),
        sa.Column("amount_mxn", sa.Integer, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_failed_payments_tenant_id", "failed_payments", ["tenant_id"])
    op.create_index("ix_failed_payments_stripe_invoice_id", "failed_payments", ["stripe_invoice_id"])
    op.create_index("ix_failed_payments_created_at", "failed_payments", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_failed_payments_created_at", table_name="failed_payments")
    op.drop_index("ix_failed_payments_stripe_invoice_id", table_name="failed_payments")
    op.drop_index("ix_failed_payments_tenant_id", table_name="failed_payments")
    op.drop_table("failed_payments")

    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_stripe_subscription_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_stripe_customer_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_tenant_id", table_name="subscriptions")
    op.drop_table("subscriptions")
