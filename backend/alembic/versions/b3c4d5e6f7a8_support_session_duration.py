"""Add requested_duration_hours to support_sessions

Revision ID: b3c4d5e6f7a8
Revises: a0b1c2d3e4f5
Create Date: 2026-05-31

"""

from alembic import op
import sqlalchemy as sa

revision = "b3c4d5e6f7a8"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "support_sessions",
        sa.Column(
            "requested_duration_hours",
            sa.Integer(),
            nullable=False,
            server_default="4",
        ),
    )


def downgrade() -> None:
    op.drop_column("support_sessions", "requested_duration_hours")
