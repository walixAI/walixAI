"""Sprint 3 schema: lead_activities, meta_lead_configs, leads/conversations/messages columns

Revision ID: f5e6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-30

Changes:
  - CREATE TABLE lead_activities
  - CREATE TABLE meta_lead_configs
  - ALTER TABLE leads  ADD COLUMNS handoff_at, handoff_by, meta_lead_id, meta_form_id, meta_ad_id
  - ALTER TABLE conversations
      ADD COLUMN current_handler VARCHAR(10) NOT NULL DEFAULT 'bot'  (replaces handled_by enum)
      ADD COLUMN handler_user_id UUID FK users.id
      MIGRATE handled_by → current_handler
      DROP COLUMN handled_by
      DROP TYPE conversation_handler
  - ALTER TABLE messages ADD COLUMN sent_by_user_id UUID FK users.id
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f5e6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. lead_activities ────────────────────────────────────────────────────
    op.create_table(
        "lead_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("activity_type", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
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
    )
    op.create_index("ix_lead_activities_lead_id", "lead_activities", ["lead_id"])
    op.create_index("ix_lead_activities_tenant_id", "lead_activities", ["tenant_id"])
    op.create_index("ix_lead_activities_actor_id", "lead_activities", ["actor_id"])
    op.create_index(
        "ix_lead_activities_activity_type", "lead_activities", ["activity_type"]
    )

    # ── 2. meta_lead_configs ──────────────────────────────────────────────────
    op.create_table(
        "meta_lead_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_id", sa.String(50), nullable=False),
        sa.Column("form_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("page_access_token", sa.Text(), nullable=False),
        sa.Column(
            "field_mapping", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
    )
    op.create_index("ix_meta_lead_configs_branch_id", "meta_lead_configs", ["branch_id"])
    op.create_index("ix_meta_lead_configs_tenant_id", "meta_lead_configs", ["tenant_id"])
    op.create_index("ix_meta_lead_configs_page_id", "meta_lead_configs", ["page_id"])

    # ── 3. leads: new columns ─────────────────────────────────────────────────
    op.add_column(
        "leads",
        sa.Column("handoff_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "handoff_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "leads",
        sa.Column("meta_lead_id", sa.String(50), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("meta_form_id", sa.String(50), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("meta_ad_id", sa.String(50), nullable=True),
    )
    op.create_index("ix_leads_meta_lead_id", "leads", ["meta_lead_id"])

    # ── 4. conversations: replace handled_by (enum) → current_handler (varchar) ──
    # Step 1: add new column as nullable so we can populate it first
    op.add_column(
        "conversations",
        sa.Column("current_handler", sa.String(10), nullable=True),
    )
    # Step 2: copy existing values (enum casts cleanly to text in PostgreSQL)
    op.execute("UPDATE conversations SET current_handler = handled_by::text")
    # Step 3: enforce NOT NULL + server default
    op.alter_column(
        "conversations",
        "current_handler",
        nullable=False,
        server_default="bot",
    )
    # Step 4: add handler_user_id FK
    op.add_column(
        "conversations",
        sa.Column(
            "handler_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conversations_handler_user_id", "conversations", ["handler_user_id"]
    )
    # Step 5: drop old column + enum type (no other table references it)
    op.drop_column("conversations", "handled_by")
    op.execute("DROP TYPE IF EXISTS conversation_handler")

    # ── 5. messages: sent_by_user_id ──────────────────────────────────────────
    op.add_column(
        "messages",
        sa.Column(
            "sent_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_messages_sent_by_user_id", "messages", ["sent_by_user_id"])


def downgrade() -> None:
    # ── 5. messages ───────────────────────────────────────────────────────────
    op.drop_index("ix_messages_sent_by_user_id", table_name="messages")
    op.drop_column("messages", "sent_by_user_id")

    # ── 4. conversations: restore handled_by enum ────────────────────────────
    op.drop_index("ix_conversations_handler_user_id", table_name="conversations")
    op.drop_column("conversations", "handler_user_id")

    op.execute(
        "CREATE TYPE conversation_handler AS ENUM ('bot', 'human')"
    )
    op.add_column(
        "conversations",
        sa.Column("handled_by", nullable=True),  # added as nullable for backfill
    )
    op.execute(
        "ALTER TABLE conversations "
        "ALTER COLUMN handled_by TYPE conversation_handler "
        "USING current_handler::conversation_handler"
    )
    op.execute(
        "UPDATE conversations SET handled_by = current_handler::conversation_handler"
    )
    op.alter_column("conversations", "handled_by", nullable=False)
    op.drop_column("conversations", "current_handler")

    # ── 3. leads ──────────────────────────────────────────────────────────────
    op.drop_index("ix_leads_meta_lead_id", table_name="leads")
    op.drop_column("leads", "meta_ad_id")
    op.drop_column("leads", "meta_form_id")
    op.drop_column("leads", "meta_lead_id")
    op.drop_column("leads", "handoff_by")
    op.drop_column("leads", "handoff_at")

    # ── 2. meta_lead_configs ──────────────────────────────────────────────────
    op.drop_index("ix_meta_lead_configs_page_id", table_name="meta_lead_configs")
    op.drop_index("ix_meta_lead_configs_tenant_id", table_name="meta_lead_configs")
    op.drop_index("ix_meta_lead_configs_branch_id", table_name="meta_lead_configs")
    op.drop_table("meta_lead_configs")

    # ── 1. lead_activities ────────────────────────────────────────────────────
    op.drop_index("ix_lead_activities_activity_type", table_name="lead_activities")
    op.drop_index("ix_lead_activities_actor_id", table_name="lead_activities")
    op.drop_index("ix_lead_activities_tenant_id", table_name="lead_activities")
    op.drop_index("ix_lead_activities_lead_id", table_name="lead_activities")
    op.drop_table("lead_activities")
