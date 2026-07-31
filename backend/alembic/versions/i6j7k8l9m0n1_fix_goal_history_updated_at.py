"""Fix: monthly_goal_history.updated_at missing — table inherits Base but migration omitted the column

BUG ENCONTRADO POR TESTS:
    MonthlyGoalHistory hereda de Base (que tiene updated_at con onupdate=func.now()),
    pero la migración g6b7c8d9e0f1 creó la tabla sin esa columna.
    SQLAlchemy emite RETURNING monthly_goal_history.updated_at en INSERTs → ProgrammingError.

    Este bug bloquea completamente los endpoints POST y PATCH /api/goals/monthly-goals.

Revision ID: i6j7k8l9m0n1
Revises: h5i6j7k8l9m0
Create Date: 2026-07-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i6j7k8l9m0n1"
down_revision = "h5i6j7k8l9m0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monthly_goal_history",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("monthly_goal_history", "updated_at")
