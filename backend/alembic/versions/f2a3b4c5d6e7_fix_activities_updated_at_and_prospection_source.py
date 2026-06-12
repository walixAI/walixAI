"""Fix: activities.updated_at missing + ck_leads_prospection_source whatsapp_inbound

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-10

Bug 1: activities table was created without updated_at column (inherited from
       Base ORM model but omitted in migration).
Bug 2: ck_leads_prospection_source constraint used 'whatsapp' but the
       LeadSource enum defines WHATSAPP_INBOUND = 'whatsapp_inbound'.
"""

import sqlalchemy as sa
from alembic import op


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Bug 2: fix prospection_source check constraint
    op.drop_constraint("ck_leads_prospection_source", "leads", type_="check")
    op.create_check_constraint(
        "ck_leads_prospection_source",
        "leads",
        "prospection_source IN ('whatsapp_inbound', 'form', 'referral', 'manual')",
    )

    # Bug 1: add missing updated_at to activities
    op.add_column(
        "activities",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("activities", "updated_at")

    op.drop_constraint("ck_leads_prospection_source", "leads", type_="check")
    op.create_check_constraint(
        "ck_leads_prospection_source",
        "leads",
        "prospection_source IN ('whatsapp', 'form', 'referral', 'manual')",
    )
