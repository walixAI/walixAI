"""drop opportunity tables

Revision ID: x1y2z3a4b5c6
Revises: w0x1y2z3a4b5
Create Date: 2026-07-28

Etapa 3 — Opportunity fue desconectado del frontend vivo. El usuario
confirmó que los datos históricos no necesitan conservarse. Las tablas
hijas (opportunity_activities, opportunity_stage_history) se eliminan
primero para respetar las FKs; la tabla padre (opportunities) al final.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "x1y2z3a4b5c6"
down_revision = "w0x1y2z3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("opportunity_activities")
    op.drop_table("opportunity_stage_history")
    op.drop_table("opportunities")


def downgrade() -> None:
    # ── Tabla padre ────────────────────────────────────────────────────────────
    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "currency", sa.String(3), nullable=False, server_default=sa.text("'MXN'")
        ),
        sa.Column("probability", sa.SmallInteger(), nullable=True),
        sa.Column("close_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(20), nullable=True),
        sa.Column(
            "status",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("won_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_reason", sa.Text(), nullable=True),
        sa.Column(
            "stage_entered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_suggestion", sa.Text(), nullable=True),
        sa.Column("ai_suggestion_urgency", sa.String(10), nullable=True),
        sa.Column("urgency_score", sa.SmallInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["stage_id"], ["pipeline_stages.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Indexes from index=True on mapped_column
    op.create_index("ix_opportunities_tenant_id", "opportunities", ["tenant_id"])
    op.create_index("ix_opportunities_branch_id", "opportunities", ["branch_id"])
    op.create_index("ix_opportunities_lead_id", "opportunities", ["lead_id"])
    op.create_index("ix_opportunities_stage_id", "opportunities", ["stage_id"])
    op.create_index("ix_opportunities_deleted_at", "opportunities", ["deleted_at"])
    # Compound indexes from __table_args__
    op.create_index(
        "ix_opp_tenant_branch_stage",
        "opportunities",
        ["tenant_id", "branch_id", "stage_id"],
    )
    op.create_index(
        "ix_opp_tenant_status", "opportunities", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_opp_tenant_close_date", "opportunities", ["tenant_id", "close_date"]
    )

    # ── Tablas hijas ───────────────────────────────────────────────────────────
    op.create_table(
        "opportunity_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opportunity_activities_tenant_id", "opportunity_activities", ["tenant_id"]
    )
    op.create_index(
        "ix_opportunity_activities_opportunity_id",
        "opportunity_activities",
        ["opportunity_id"],
    )
    op.create_index(
        "ix_opportunity_activities_type", "opportunity_activities", ["type"]
    )

    op.create_table(
        "opportunity_stage_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_stage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["from_stage_id"], ["pipeline_stages.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["to_stage_id"], ["pipeline_stages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opportunity_stage_history_tenant_id",
        "opportunity_stage_history",
        ["tenant_id"],
    )
    op.create_index(
        "ix_opportunity_stage_history_opportunity_id",
        "opportunity_stage_history",
        ["opportunity_id"],
    )
