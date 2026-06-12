"""Add failed_tasks table for Celery dead-letter queue.

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-06-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "i5j6k7l8m9n0"
down_revision = "h4i5j6k7l8m9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failed_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.String(255), nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_failed_tasks_task_id"),
    )
    op.create_index("ix_failed_tasks_task_id", "failed_tasks", ["task_id"])
    op.create_index("ix_failed_tasks_task_name", "failed_tasks", ["task_name"])


def downgrade() -> None:
    op.drop_index("ix_failed_tasks_task_name", table_name="failed_tasks")
    op.drop_index("ix_failed_tasks_task_id", table_name="failed_tasks")
    op.drop_table("failed_tasks")
