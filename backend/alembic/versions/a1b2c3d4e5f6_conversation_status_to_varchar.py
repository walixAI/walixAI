"""Convert conversations.status from conversation_status enum to VARCHAR(10)

Revision ID: a1b2c3d4e5f6
Revises: f5e6a7b8c9d0
Create Date: 2026-05-30

The model already declares status as String(10); this migration makes the DB
match so that asyncpg prepared-statement type checks don't fail on comparisons
like `status != 'closed'` (operator does not exist: conversation_status <> varchar).
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f5e6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Convert in-place: enum values cast cleanly to text in PostgreSQL
    op.execute(
        "ALTER TABLE conversations "
        "ALTER COLUMN status TYPE VARCHAR(10) "
        "USING status::text"
    )
    op.execute("DROP TYPE IF EXISTS conversation_status")


def downgrade() -> None:
    op.execute(
        "CREATE TYPE conversation_status AS ENUM ('active', 'handoff', 'closed')"
    )
    op.execute(
        "ALTER TABLE conversations "
        "ALTER COLUMN status TYPE conversation_status "
        "USING status::conversation_status"
    )
