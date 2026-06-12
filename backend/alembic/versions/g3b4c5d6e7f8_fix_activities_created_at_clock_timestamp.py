"""Fix: activities created_at/updated_at use clock_timestamp() not now()

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-06-10

now() returns the transaction start time — all rows inserted in the same
transaction share the same value. clock_timestamp() returns the real wall-clock
time at each statement, making ORDER BY created_at DESC deterministic even
for rows inserted within the same outer transaction (as happens in tests).
"""

from alembic import op


revision = "g3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE activities "
        "ALTER COLUMN created_at SET DEFAULT clock_timestamp()"
    )
    op.execute(
        "ALTER TABLE activities "
        "ALTER COLUMN updated_at SET DEFAULT clock_timestamp()"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE activities "
        "ALTER COLUMN created_at SET DEFAULT now()"
    )
    op.execute(
        "ALTER TABLE activities "
        "ALTER COLUMN updated_at SET DEFAULT now()"
    )
