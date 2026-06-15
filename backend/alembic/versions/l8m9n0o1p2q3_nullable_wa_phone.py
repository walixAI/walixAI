"""Hacer wa_phone nullable en leads — el campo queda en blanco si no se proporciona teléfono.

Revision ID: l8m9n0o1p2q3
Revises: k7l8m9n0o1p2
Create Date: 2026-06-14
"""

import sqlalchemy as sa
from alembic import op

revision = "l8m9n0o1p2q3"
down_revision = "k7l8m9n0o1p2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Primero hacer nullable, luego limpiar prefijos NOPHONE_
    op.alter_column("leads", "wa_phone", existing_type=sa.String(32), nullable=True)
    op.execute(
        "UPDATE leads SET wa_phone = NULL WHERE wa_phone LIKE 'NOPHONE_%'"
    )


def downgrade() -> None:
    # Rellenar NULLs con placeholder antes de revertir NOT NULL
    op.execute(
        "UPDATE leads SET wa_phone = 'NOPHONE_' || gen_random_uuid()::text WHERE wa_phone IS NULL"
    )
    op.alter_column("leads", "wa_phone", existing_type=sa.String(32), nullable=False)
