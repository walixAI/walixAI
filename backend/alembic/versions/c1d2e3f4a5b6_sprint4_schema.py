"""Sprint 4 schema — ai_config on branches, pipeline_stages, onboarding_drafts

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f6a7
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "c1d2e3f4a5b6"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. branches — AI config & onboarding columns ──────────────────────────
    op.add_column("branches", sa.Column("ai_config", JSONB, nullable=True))
    op.add_column("branches", sa.Column("industry", sa.String(30), nullable=True))
    op.add_column(
        "branches",
        sa.Column(
            "onboarding_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("branches", sa.Column("bot_name", sa.String(50), nullable=True))
    op.add_column(
        "branches", sa.Column("business_description", sa.Text, nullable=True)
    )

    # ── 2. pipeline_stages ────────────────────────────────────────────────────
    op.create_table(
        "pipeline_stages",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "branch_id",
            UUID(as_uuid=True),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column(
            "is_won", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_lost", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("auto_advance_criteria", sa.Text, nullable=True),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_pipeline_stages_branch_id", "pipeline_stages", ["branch_id"])
    op.create_index("ix_pipeline_stages_tenant_id", "pipeline_stages", ["tenant_id"])
    op.create_unique_constraint(
        "uq_pipeline_stages_branch_slug", "pipeline_stages", ["branch_id", "slug"]
    )

    # ── 3. onboarding_drafts ──────────────────────────────────────────────────
    op.create_table(
        "onboarding_drafts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "branch_id",
            UUID(as_uuid=True),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generated_config", JSONB, nullable=False, server_default="{}"),
        sa.Column("business_input", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column(
            "approved_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_onboarding_drafts_branch_id", "onboarding_drafts", ["branch_id"])
    op.create_index("ix_onboarding_drafts_tenant_id", "onboarding_drafts", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("onboarding_drafts")
    op.drop_table("pipeline_stages")
    op.drop_column("branches", "business_description")
    op.drop_column("branches", "bot_name")
    op.drop_column("branches", "onboarding_status")
    op.drop_column("branches", "industry")
    op.drop_column("branches", "ai_config")
