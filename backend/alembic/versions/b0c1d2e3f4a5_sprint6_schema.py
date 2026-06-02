"""Sprint 6 schema: agent_suggestions, lead_scores, daily_metrics, sentiment_snapshots, leads score columns

Revision ID: b0c1d2e3f4a5
Revises: a0b1c2d3e4f5
Create Date: 2026-06-02

Changes:
  - CREATE TABLE agent_suggestions
  - CREATE TABLE lead_scores
  - CREATE TABLE daily_metrics  (UNIQUE branch_id + metric_date)
  - CREATE TABLE sentiment_snapshots  (UNIQUE branch_id + snapshot_date)
  - ALTER TABLE leads ADD COLUMNS current_score, current_score_trend
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b0c1d2e3f4a5"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. agent_suggestions ─────────────────────────────────────────────────
    op.create_table(
        "agent_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("trigger_description", sa.Text(), nullable=False),
        sa.Column("suggestion_text", sa.Text(), nullable=False),
        sa.Column("action_payload", postgresql.JSONB(), nullable=True),
        sa.Column("target_role", sa.String(30), nullable=False),
        sa.Column(
            "target_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="suggested",
        ),
        sa.Column("execution_result", postgresql.JSONB(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
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
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW() + INTERVAL '48 hours'"),
        ),
    )
    op.create_index("ix_agent_suggestions_tenant_id", "agent_suggestions", ["tenant_id"])
    op.create_index("ix_agent_suggestions_agent_type", "agent_suggestions", ["agent_type"])
    op.create_index("ix_agent_suggestions_target_role", "agent_suggestions", ["target_role"])
    op.create_index(
        "ix_agent_suggestions_target_user_id", "agent_suggestions", ["target_user_id"]
    )
    op.create_index("ix_agent_suggestions_status", "agent_suggestions", ["status"])

    # ── 2. lead_scores ───────────────────────────────────────────────────────
    op.create_table(
        "lead_scores",
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
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column(
            "positive_factors",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "negative_factors",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("main_reason", sa.Text(), nullable=False),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
    op.create_index("ix_lead_scores_lead_id", "lead_scores", ["lead_id"])
    op.create_index("ix_lead_scores_tenant_id", "lead_scores", ["tenant_id"])
    op.create_index("ix_lead_scores_calculated_at", "lead_scores", ["calculated_at"])

    # ── 3. daily_metrics ─────────────────────────────────────────────────────
    op.create_table(
        "daily_metrics",
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
        sa.Column("metric_date", sa.Date(), nullable=False),
        # Lead funnel
        sa.Column("leads_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("leads_qualified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("leads_won", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("leads_lost", sa.Integer(), nullable=False, server_default="0"),
        # Messaging
        sa.Column("messages_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_received", sa.Integer(), nullable=False, server_default="0"),
        # Activities
        sa.Column("calls_logged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quotes_sent", sa.Integer(), nullable=False, server_default="0"),
        # Response time
        sa.Column(
            "avg_first_response_sec", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "metrics_by_agent",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
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
        sa.UniqueConstraint("branch_id", "metric_date", name="uq_daily_metrics_branch_date"),
    )
    op.create_index("ix_daily_metrics_branch_id", "daily_metrics", ["branch_id"])

    # ── 4. sentiment_snapshots ───────────────────────────────────────────────
    op.create_table(
        "sentiment_snapshots",
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
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column(
            "distribution", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("by_stage", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("by_agent", postgresql.JSONB(), nullable=False, server_default="{}"),
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
        sa.UniqueConstraint(
            "branch_id", "snapshot_date", name="uq_sentiment_snapshots_branch_date"
        ),
    )
    op.create_index(
        "ix_sentiment_snapshots_branch_id", "sentiment_snapshots", ["branch_id"]
    )

    # ── 5. leads: prediction score columns ───────────────────────────────────
    op.add_column("leads", sa.Column("current_score", sa.SmallInteger(), nullable=True))
    op.add_column(
        "leads", sa.Column("current_score_trend", sa.String(4), nullable=True)
    )


def downgrade() -> None:
    # ── 5. leads ──────────────────────────────────────────────────────────────
    op.drop_column("leads", "current_score_trend")
    op.drop_column("leads", "current_score")

    # ── 4. sentiment_snapshots ───────────────────────────────────────────────
    op.drop_index("ix_sentiment_snapshots_branch_id", table_name="sentiment_snapshots")
    op.drop_table("sentiment_snapshots")

    # ── 3. daily_metrics ─────────────────────────────────────────────────────
    op.drop_index("ix_daily_metrics_branch_id", table_name="daily_metrics")
    op.drop_table("daily_metrics")

    # ── 2. lead_scores ───────────────────────────────────────────────────────
    op.drop_index("ix_lead_scores_calculated_at", table_name="lead_scores")
    op.drop_index("ix_lead_scores_tenant_id", table_name="lead_scores")
    op.drop_index("ix_lead_scores_lead_id", table_name="lead_scores")
    op.drop_table("lead_scores")

    # ── 1. agent_suggestions ─────────────────────────────────────────────────
    op.drop_index("ix_agent_suggestions_status", table_name="agent_suggestions")
    op.drop_index(
        "ix_agent_suggestions_target_user_id", table_name="agent_suggestions"
    )
    op.drop_index("ix_agent_suggestions_target_role", table_name="agent_suggestions")
    op.drop_index("ix_agent_suggestions_agent_type", table_name="agent_suggestions")
    op.drop_index("ix_agent_suggestions_tenant_id", table_name="agent_suggestions")
    op.drop_table("agent_suggestions")
