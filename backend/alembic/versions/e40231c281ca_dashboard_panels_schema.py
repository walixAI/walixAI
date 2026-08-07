"""dashboard_panels schema + generalizar dashboard_layouts por panel

Revision ID: e40231c281ca
Revises: 2b3c4d5e6f7g
Create Date: 2026-08-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e40231c281ca"
down_revision = "2b3c4d5e6f7g"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. dashboard_panels ────────────────────────────────────────────────────
    op.create_table(
        "dashboard_panels",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("min_role", sa.String(50), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dashboard_panels_tenant_id", "dashboard_panels", ["tenant_id"])
    op.create_index("ix_dashboard_panels_created_by", "dashboard_panels", ["created_by"])

    # Partial unique index for system panels: UNIQUE(tenant_id, key) WHERE is_system = true
    op.create_index(
        "uq_dashboard_panels_system_tenant_key",
        "dashboard_panels",
        ["tenant_id", "key"],
        unique=True,
        postgresql_where=sa.text("is_system = true"),
    )
    # Partial unique index for custom panels: UNIQUE(tenant_id, created_by, key) WHERE is_system = false
    op.create_index(
        "uq_dashboard_panels_custom_tenant_creator_key",
        "dashboard_panels",
        ["tenant_id", "created_by", "key"],
        unique=True,
        postgresql_where=sa.text("is_system = false"),
    )

    # ── 2. Seed 2 system panels per existing tenant ────────────────────────────
    bind = op.get_bind()
    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]

    panels_table = sa.table(
        "dashboard_panels",
        sa.column("tenant_id", sa.UUID()),
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("icon", sa.String),
        sa.column("min_role", sa.String),
        sa.column("is_system", sa.Boolean),
        sa.column("position", sa.Integer),
        sa.column("created_by", sa.UUID()),
    )
    rows = []
    for tid in tenant_ids:
        rows.append({
            "tenant_id": tid, "key": "principal", "name": "Principal",
            "icon": None, "min_role": None, "is_system": True,
            "position": 0, "created_by": None,
        })
        rows.append({
            "tenant_id": tid, "key": "desempeno", "name": "Desempeño",
            "icon": None, "min_role": "owner", "is_system": True,
            "position": 1, "created_by": None,
        })
    if rows:
        op.bulk_insert(panels_table, rows)

    # ── 3. dashboard_layouts — add panel_key (server_default backfills existing rows) ──
    op.add_column(
        "dashboard_layouts",
        sa.Column("panel_key", sa.String(100), nullable=False, server_default="principal"),
    )

    # ── 4. Replace unique constraint to include panel_key ─────────────────────
    op.drop_constraint("uq_dashboard_layouts_tenant_scope", "dashboard_layouts", type_="unique")
    op.create_unique_constraint(
        "uq_dashboard_layouts_tenant_panel_scope",
        "dashboard_layouts",
        ["tenant_id", "panel_key", "scope"],
    )


def downgrade() -> None:
    # Restore old unique constraint on dashboard_layouts
    op.drop_constraint("uq_dashboard_layouts_tenant_panel_scope", "dashboard_layouts", type_="unique")
    op.create_unique_constraint(
        "uq_dashboard_layouts_tenant_scope",
        "dashboard_layouts",
        ["tenant_id", "scope"],
    )

    # Drop panel_key column
    op.drop_column("dashboard_layouts", "panel_key")

    # Drop dashboard_panels (indexes first)
    op.drop_index("uq_dashboard_panels_custom_tenant_creator_key", table_name="dashboard_panels")
    op.drop_index("uq_dashboard_panels_system_tenant_key", table_name="dashboard_panels")
    op.drop_index("ix_dashboard_panels_created_by", table_name="dashboard_panels")
    op.drop_index("ix_dashboard_panels_tenant_id", table_name="dashboard_panels")
    op.drop_table("dashboard_panels")
