"""message_templates — catálogo de plantillas WhatsApp por sucursal/tenant

Revision ID: 1a2b3c4d5e6f
Revises: k8l9m0n1o2p3
Create Date: 2026-08-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "1a2b3c4d5e6f"
down_revision = "k8l9m0n1o2p3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("language", sa.String(20), nullable=False, server_default="es_MX"),
        sa.Column("category", sa.String(100), nullable=False, server_default="General"),
        sa.Column("body_preview", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_templates_tenant_id", "message_templates", ["tenant_id"])
    op.create_index("ix_message_templates_branch_id", "message_templates", ["branch_id"])


def downgrade() -> None:
    op.drop_index("ix_message_templates_branch_id", table_name="message_templates")
    op.drop_index("ix_message_templates_tenant_id", table_name="message_templates")
    op.drop_table("message_templates")
