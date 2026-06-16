"""Sprint 9 — tenant registration fields + trial plan.

Adds:
  tenants.trial_ends_at             TIMESTAMPTZ nullable
  tenants.registration_completed_at TIMESTAMPTZ nullable
  tenants.stripe_customer_id        VARCHAR(100) nullable
  tenants.referral_source           VARCHAR(100) nullable
  users.email_verified_at           TIMESTAMPTZ nullable
  tenant_plan enum value 'trial'

Revision ID: m9n0o1p2q3r4
Revises: l8m9n0o1p2q3
Create Date: 2026-06-15
"""

import sqlalchemy as sa
from alembic import op

revision = "m9n0o1p2q3r4"
down_revision = "l8m9n0o1p2q3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add 'trial' to tenant_plan enum ───────────────────────────────────
    # PostgreSQL 16 supports ADD VALUE inside a transaction.
    # IF NOT EXISTS makes this idempotent (safe to re-run).
    op.execute(sa.text("ALTER TYPE tenant_plan ADD VALUE IF NOT EXISTS 'trial' BEFORE 'starter'"))

    # ── 2. New columns on tenants ─────────────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("registration_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("stripe_customer_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("referral_source", sa.String(100), nullable=True),
    )
    op.create_index("ix_tenants_trial_ends_at", "tenants", ["trial_ends_at"])
    op.create_index("ix_tenants_stripe_customer_id", "tenants", ["stripe_customer_id"])

    # ── 3. New column on users ────────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")

    op.drop_index("ix_tenants_stripe_customer_id", table_name="tenants")
    op.drop_index("ix_tenants_trial_ends_at", table_name="tenants")
    op.drop_column("tenants", "referral_source")
    op.drop_column("tenants", "stripe_customer_id")
    op.drop_column("tenants", "registration_completed_at")
    op.drop_column("tenants", "trial_ends_at")

    # Note: PostgreSQL does not support removing enum values.
    # 'trial' will remain in the enum after downgrade.
