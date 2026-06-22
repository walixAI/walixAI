"""Sprint 14C.1 — default_probability en pipeline_stages.

Revision ID: u8v9w0x1y2z3
Revises: t7u8v9w0x1y2
Create Date: 2026-06-21

Cambios:
  1. Rellena NULLs en probability_default con valores graduales:
       - Etapas won  → 100
       - Etapas lost → 0
       - Etapas open → gradual 10..90 según posición (order_index)
  2. ALTER TABLE pipeline_stages: SET NOT NULL, SET DEFAULT 0
"""

from alembic import op
from sqlalchemy import text

revision = "u8v9w0x1y2z3"
down_revision = "t7u8v9w0x1y2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Won stages → 100
    conn.execute(text("""
        UPDATE pipeline_stages
        SET probability_default = 100
        WHERE is_won = TRUE AND probability_default IS NULL
    """))

    # 2. Lost stages → 0
    conn.execute(text("""
        UPDATE pipeline_stages
        SET probability_default = 0
        WHERE is_lost = TRUE AND probability_default IS NULL
    """))

    # 3. Open stages: graduated 10..90 by order_index rank within each tenant
    conn.execute(text("""
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY order_index) AS rn,
                COUNT(*)     OVER (PARTITION BY tenant_id)                       AS total
            FROM pipeline_stages
            WHERE NOT is_won AND NOT is_lost AND probability_default IS NULL
        )
        UPDATE pipeline_stages p
        SET probability_default = CASE
            WHEN ranked.total = 1 THEN 50
            ELSE LEAST(90, GREATEST(10,
                ((ranked.rn - 1) * 80 / (ranked.total - 1)) + 10
            ))
        END
        FROM ranked
        WHERE p.id = ranked.id
    """))

    # 4. Remaining NULLs (edge case) → 0
    conn.execute(text("""
        UPDATE pipeline_stages
        SET probability_default = 0
        WHERE probability_default IS NULL
    """))

    # 5. Make NOT NULL with server default 0
    conn.execute(text(
        "ALTER TABLE pipeline_stages ALTER COLUMN probability_default SET NOT NULL"
    ))
    conn.execute(text(
        "ALTER TABLE pipeline_stages ALTER COLUMN probability_default SET DEFAULT 0"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE pipeline_stages ALTER COLUMN probability_default DROP NOT NULL"
    ))
    conn.execute(text(
        "ALTER TABLE pipeline_stages ALTER COLUMN probability_default DROP DEFAULT"
    ))
