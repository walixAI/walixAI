"""Sprint 4 T-29 — add pipeline_stage_id to leads

Revision ID: d5e6f7a8b9c0
Revises: c1d2e3f4a5b6
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "d5e6f7a8b9c0"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "pipeline_stage_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pipeline_stages.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_leads_pipeline_stage_id", "leads", ["pipeline_stage_id"])


def downgrade() -> None:
    op.drop_index("ix_leads_pipeline_stage_id", table_name="leads")
    op.drop_column("leads", "pipeline_stage_id")
