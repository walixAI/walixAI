"""activity task fields — task_kind, assignee_id, deal_id, closed_via, closed_note

Revision ID: z3a4b5c6d7e8
Revises: y2z3a4b5c6d7
Create Date: 2026-07-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "z3a4b5c6d7e8"
down_revision = "y2z3a4b5c6d7"
branch_labels = None
depends_on = None

_TASK_KINDS = (
    "cobro", "cotizacion", "servicio", "seguimiento",
    "queja", "refaccion", "facturacion", "devolucion", "otro",
)
_CLOSED_VIA = ("whatsapp", "email", "call", "manual", "auto", "other")


def upgrade() -> None:
    # 1. Columns — bare types only, no inline ForeignKey
    op.add_column("activities", sa.Column("task_kind", sa.String(20), nullable=True))
    op.add_column("activities", sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("activities", sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("activities", sa.Column("closed_via", sa.String(20), nullable=True))
    op.add_column("activities", sa.Column("closed_note", sa.Text(), nullable=True))

    # 2. Foreign keys — named explicitly to avoid anonymous constraints
    op.create_foreign_key(
        "fk_activities_assignee_id_users",
        "activities", "users", ["assignee_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_activities_deal_id_deals",
        "activities", "deals", ["deal_id"], ["id"],
        ondelete="SET NULL",
    )

    # 3. Indexes
    op.create_index("ix_activities_assignee_id", "activities", ["assignee_id"])
    op.create_index("ix_activities_deal_id", "activities", ["deal_id"])

    # 4. CHECK constraints
    kinds_list = ", ".join(f"'{k}'" for k in _TASK_KINDS)
    op.create_check_constraint(
        "ck_activities_task_kind",
        "activities",
        f"task_kind IS NULL OR task_kind IN ({kinds_list})",
    )
    via_list = ", ".join(f"'{v}'" for v in _CLOSED_VIA)
    op.create_check_constraint(
        "ck_activities_closed_via",
        "activities",
        f"closed_via IS NULL OR closed_via IN ({via_list})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_activities_closed_via", "activities", type_="check")
    op.drop_constraint("ck_activities_task_kind", "activities", type_="check")
    op.drop_index("ix_activities_deal_id", table_name="activities")
    op.drop_index("ix_activities_assignee_id", table_name="activities")
    op.drop_constraint("fk_activities_deal_id_deals", "activities", type_="foreignkey")
    op.drop_constraint("fk_activities_assignee_id_users", "activities", type_="foreignkey")
    op.drop_column("activities", "closed_note")
    op.drop_column("activities", "closed_via")
    op.drop_column("activities", "deal_id")
    op.drop_column("activities", "assignee_id")
    op.drop_column("activities", "task_kind")
