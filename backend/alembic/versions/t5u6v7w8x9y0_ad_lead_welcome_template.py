"""Prompt Utel #2 — branches.ad_lead_welcome_template.

Agrega:
  branches.ad_lead_welcome_template  TEXT nullable

Mensaje de bienvenida configurable por branch para leads que llegan vía
Meta/Google Ads, con soporte para el placeholder {name}. Reemplaza el texto
hardcodeado ("Clínica de Endocrinología Pediátrica") que tenía
app/api/webhooks.py::_send_meta_lead_welcome — si la columna es None, el
código usa un fallback genérico (ver _build_ad_lead_welcome_message en
webhooks.py), nunca un texto de negocio específico.

Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from alembic import op

revision = "t5u6v7w8x9y0"
down_revision = "s4t5u6v7w8x9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "branches",
        sa.Column("ad_lead_welcome_template", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("branches", "ad_lead_welcome_template")
