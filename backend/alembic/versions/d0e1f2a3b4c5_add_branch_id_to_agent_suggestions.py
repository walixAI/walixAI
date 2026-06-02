"""Add branch_id to agent_suggestions

Revision ID: d0e1f2a3b4c5
Revises: b0c1d2e3f4a5
Create Date: 2026-06-02

Changes:
  - ALTER TABLE agent_suggestions ADD COLUMN branch_id UUID REFERENCES branches(id) ON DELETE SET NULL
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d0e1f2a3b4c5"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_suggestions",
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("branches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_agent_suggestions_branch_id", "agent_suggestions", ["branch_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_suggestions_branch_id", table_name="agent_suggestions")
    op.drop_column("agent_suggestions", "branch_id")
