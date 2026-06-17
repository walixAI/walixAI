"""Sprint 12 — KB document management: is_auto_generated + content.

Agrega a knowledge_documents:
  is_auto_generated  BOOLEAN DEFAULT FALSE NOT NULL
  content            TEXT nullable

Revision ID: q3r4s5t6u7v8
Revises: p2q3r4s5t6u7
Create Date: 2026-06-16
"""

import sqlalchemy as sa
from alembic import op

revision = "q3r4s5t6u7v8"
down_revision = "p2q3r4s5t6u7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("is_auto_generated", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("content", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_documents", "content")
    op.drop_column("knowledge_documents", "is_auto_generated")
