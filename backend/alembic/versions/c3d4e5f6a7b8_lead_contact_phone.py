"""Add contact_phone to leads

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-05-29

"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("contact_phone", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "contact_phone")
