"""Sprint 5 schema: alert_rules, ai_command_logs, support_sessions, leads risk columns

Revision ID: a0b1c2d3e4f5
Revises: d5e6f7a8b9c0
Create Date: 2026-05-31

Changes:
  - CREATE TABLE alert_rules
  - CREATE TABLE ai_command_logs
  - CREATE TABLE support_sessions
  - ALTER TABLE leads ADD COLUMNS risk_score, risk_reason, last_alert_at
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a0b1c2d3e4f5"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. alert_rules ────────────────────────────────────────────────────────
    op.create_table(
        "alert_rules",
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
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("alert_type", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("schedule_hour", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("silence_start", sa.Integer(), nullable=False, server_default="21"),
        sa.Column("silence_end", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("threshold_hours", sa.Integer(), nullable=False, server_default="48"),
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
    op.create_index("ix_alert_rules_branch_id", "alert_rules", ["branch_id"])
    op.create_index("ix_alert_rules_tenant_id", "alert_rules", ["tenant_id"])
    op.create_index("ix_alert_rules_user_id", "alert_rules", ["user_id"])
    op.create_index("ix_alert_rules_alert_type", "alert_rules", ["alert_type"])

    # ── 2. ai_command_logs ────────────────────────────────────────────────────
    op.create_table(
        "ai_command_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("intent_type", sa.String(20), nullable=False),
        sa.Column("screen_context", sa.String(50), nullable=True),
        sa.Column("actions_taken", postgresql.JSONB(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
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
    op.create_index("ix_ai_command_logs_user_id", "ai_command_logs", ["user_id"])
    op.create_index("ix_ai_command_logs_tenant_id", "ai_command_logs", ["tenant_id"])
    op.create_index("ix_ai_command_logs_intent_type", "ai_command_logs", ["intent_type"])

    # ── 3. support_sessions ───────────────────────────────────────────────────
    op.create_table(
        "support_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "support_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("access_code", sa.String(6), nullable=False),
        sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "scope", sa.String(20), nullable=False, server_default="readonly"
        ),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column(
            "authorized_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actions_log",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
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
    op.create_index(
        "ix_support_sessions_support_user_id", "support_sessions", ["support_user_id"]
    )
    op.create_index(
        "ix_support_sessions_tenant_id", "support_sessions", ["tenant_id"]
    )
    op.create_index(
        "ix_support_sessions_status", "support_sessions", ["status"]
    )

    # ── 4. leads: risk + alert columns ───────────────────────────────────────
    op.add_column("leads", sa.Column("risk_score", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("risk_reason", sa.Text(), nullable=True))
    op.add_column(
        "leads",
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # ── 4. leads ──────────────────────────────────────────────────────────────
    op.drop_column("leads", "last_alert_at")
    op.drop_column("leads", "risk_reason")
    op.drop_column("leads", "risk_score")

    # ── 3. support_sessions ───────────────────────────────────────────────────
    op.drop_index("ix_support_sessions_status", table_name="support_sessions")
    op.drop_index("ix_support_sessions_tenant_id", table_name="support_sessions")
    op.drop_index(
        "ix_support_sessions_support_user_id", table_name="support_sessions"
    )
    op.drop_table("support_sessions")

    # ── 2. ai_command_logs ────────────────────────────────────────────────────
    op.drop_index("ix_ai_command_logs_intent_type", table_name="ai_command_logs")
    op.drop_index("ix_ai_command_logs_tenant_id", table_name="ai_command_logs")
    op.drop_index("ix_ai_command_logs_user_id", table_name="ai_command_logs")
    op.drop_table("ai_command_logs")

    # ── 1. alert_rules ────────────────────────────────────────────────────────
    op.drop_index("ix_alert_rules_alert_type", table_name="alert_rules")
    op.drop_index("ix_alert_rules_user_id", table_name="alert_rules")
    op.drop_index("ix_alert_rules_tenant_id", table_name="alert_rules")
    op.drop_index("ix_alert_rules_branch_id", table_name="alert_rules")
    op.drop_table("alert_rules")
