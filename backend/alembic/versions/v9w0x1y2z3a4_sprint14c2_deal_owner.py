"""Sprint 14C.2 — owner_id en deals (dueño del deal).

Revision ID: v9w0x1y2z3a4
Revises: u8v9w0x1y2z3
Create Date: 2026-06-21

Cambios:
  1. ALTER TABLE deals ADD COLUMN owner_id UUID NULL REFERENCES users(id) ON DELETE SET NULL.
  2. CREATE INDEX ix_deals_owner_id ON deals (owner_id).
  3. Deals existentes quedan con owner_id = NULL (sin asignar).
  downgrade: DROP INDEX + DROP COLUMN.
"""

from alembic import op
from sqlalchemy import text

revision = "v9w0x1y2z3a4"
down_revision = "u8v9w0x1y2z3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE deals
        ADD COLUMN IF NOT EXISTS owner_id UUID NULL
        REFERENCES users(id) ON DELETE SET NULL
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_deals_owner_id ON deals (owner_id)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_deals_owner_id"))
    conn.execute(text("ALTER TABLE deals DROP COLUMN IF EXISTS owner_id"))
