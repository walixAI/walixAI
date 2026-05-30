"""Convert messages.role from message_role enum to VARCHAR(16)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-30

The model declares role as String(16); the DB still has message_role enum.
asyncpg prepared statements reject INSERT/UPDATE of varchar into enum columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE messages "
        "ALTER COLUMN role TYPE VARCHAR(16) "
        "USING role::text"
    )
    op.execute("DROP TYPE IF EXISTS message_role")


def downgrade() -> None:
    op.execute(
        "CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system')"
    )
    op.execute(
        "ALTER TABLE messages "
        "ALTER COLUMN role TYPE message_role "
        "USING role::message_role"
    )
