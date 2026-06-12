"""Sprint 7 T-01 — Contacts schema: leads extensions + activities + tags + lead_tags

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5, c4d5e6f7a8b9   (merges both heads)
Create Date: 2026-06-09

Changes:
  1. ALTER TABLE leads — last_name, company, prospection_source, deleted_at,
                         last_activity_summary  +  ix_leads_company, ix_leads_deleted_at
  2. CREATE TABLE activities  +  4 indexes (incl. partial on due_date)
  3. CREATE TABLE tags        +  unique (tenant_id, name)  +  ix_tags_tenant_id
  4. CREATE TABLE lead_tags   +  composite PK (lead_id, tag_id)  +  2 indexes
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e1f2a3b4c5d6"
down_revision = ("d0e1f2a3b4c5", "c4d5e6f7a8b9")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. ALTER TABLE leads ──────────────────────────────────────────────────
    op.add_column("leads", sa.Column("last_name", sa.String(120), nullable=True))
    op.add_column("leads", sa.Column("company", sa.String(200), nullable=True))
    op.add_column(
        "leads",
        sa.Column(
            "prospection_source",
            sa.String(30),
            nullable=False,
            server_default="manual",
        ),
    )
    op.create_check_constraint(
        "ck_leads_prospection_source",
        "leads",
        "prospection_source IN ('whatsapp', 'form', 'referral', 'manual')",
    )
    op.add_column(
        "leads",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("last_activity_summary", sa.Text(), nullable=True),
    )
    op.create_index("ix_leads_company", "leads", ["company"])
    op.create_index("ix_leads_deleted_at", "leads", ["deleted_at"])

    # ── 2. CREATE TABLE activities ────────────────────────────────────────────
    op.create_table(
        "activities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("activity_type", sa.String(20), nullable=False),
        sa.CheckConstraint(
            "activity_type IN ('note', 'task', 'call', 'meeting', 'email', 'system')",
            name="ck_activities_activity_type",
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_activities_lead_id_created_at",
        "activities",
        ["lead_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_activities_tenant_id", "activities", ["tenant_id"])
    op.create_index("ix_activities_activity_type", "activities", ["activity_type"])
    op.create_index(
        "ix_activities_due_date",
        "activities",
        ["due_date"],
        postgresql_where=sa.text("due_date IS NOT NULL"),
    )

    # ── 3. CREATE TABLE tags ──────────────────────────────────────────────────
    op.create_table(
        "tags",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),
    )
    op.create_index("ix_tags_tenant_id", "tags", ["tenant_id"])

    # ── 4. CREATE TABLE lead_tags (pivot) ─────────────────────────────────────
    op.create_table(
        "lead_tags",
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("lead_id", "tag_id", name="pk_lead_tags"),
    )
    op.create_index("ix_lead_tags_tag_id", "lead_tags", ["tag_id"])
    op.create_index("ix_lead_tags_lead_id", "lead_tags", ["lead_id"])


def downgrade() -> None:
    # ── 4. lead_tags ──────────────────────────────────────────────────────────
    op.drop_index("ix_lead_tags_lead_id", table_name="lead_tags")
    op.drop_index("ix_lead_tags_tag_id", table_name="lead_tags")
    op.drop_table("lead_tags")

    # ── 3. tags ───────────────────────────────────────────────────────────────
    op.drop_index("ix_tags_tenant_id", table_name="tags")
    op.drop_table("tags")

    # ── 2. activities ─────────────────────────────────────────────────────────
    op.drop_index("ix_activities_due_date", table_name="activities")
    op.drop_index("ix_activities_activity_type", table_name="activities")
    op.drop_index("ix_activities_tenant_id", table_name="activities")
    op.drop_index("ix_activities_lead_id_created_at", table_name="activities")
    op.drop_table("activities")

    # ── 1. leads ──────────────────────────────────────────────────────────────
    op.drop_index("ix_leads_deleted_at", table_name="leads")
    op.drop_index("ix_leads_company", table_name="leads")
    op.drop_column("leads", "last_activity_summary")
    op.drop_column("leads", "deleted_at")
    op.drop_constraint("ck_leads_prospection_source", "leads", type_="check")
    op.drop_column("leads", "prospection_source")
    op.drop_column("leads", "company")
    op.drop_column("leads", "last_name")
