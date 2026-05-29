"""Add 'doctor' value to user_role enum

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-29

"""
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 9.6+ supports IF NOT EXISTS — safe to re-run
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'doctor'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op.
    pass
