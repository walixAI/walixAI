"""Sprint 14A — Ampliar deals + tabla deal_stage_history con RLS.

Revision ID: t7u8v9w0x1y2
Revises: s6t7u8v9w0x1
Create Date: 2026-06-19

Cambios:
  1. ALTER TABLE deals ADD COLUMN source, notes, lost_reason, lost_comment.
  2. CREATE TABLE deal_stage_history + índices + RLS (4 políticas).
"""

from alembic import op
from sqlalchemy import text

revision = "t7u8v9w0x1y2"
down_revision = "s6t7u8v9w0x1"
branch_labels = None
depends_on = None

_TENANT_EXPR = "current_setting('app.current_tenant_id', TRUE)::uuid"


def _enable_rls(conn, table: str) -> None:
    conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_select ON {table}"
        f"  FOR SELECT USING (tenant_id = {_TENANT_EXPR})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_insert ON {table}"
        f"  FOR INSERT WITH CHECK (tenant_id = {_TENANT_EXPR})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_update ON {table}"
        f"  FOR UPDATE USING (tenant_id = {_TENANT_EXPR})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_delete ON {table}"
        f"  FOR DELETE USING (tenant_id = {_TENANT_EXPR})"
    ))


def _disable_rls(conn, table: str) -> None:
    for op_type in ("select", "insert", "update", "delete"):
        conn.execute(text(
            f"DROP POLICY IF EXISTS tenant_isolation_{op_type} ON {table}"
        ))
    conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    conn.execute(text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Nuevas columnas en deals (todas nullable — backward-compat)
    conn.execute(text("ALTER TABLE deals ADD COLUMN IF NOT EXISTS source       VARCHAR(50)"))
    conn.execute(text("ALTER TABLE deals ADD COLUMN IF NOT EXISTS notes        TEXT"))
    conn.execute(text("ALTER TABLE deals ADD COLUMN IF NOT EXISTS lost_reason  VARCHAR(30)"))
    conn.execute(text("ALTER TABLE deals ADD COLUMN IF NOT EXISTS lost_comment TEXT"))

    # 2. deal_stage_history
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS deal_stage_history (
            id            UUID        NOT NULL DEFAULT gen_random_uuid(),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            tenant_id     UUID        NOT NULL REFERENCES tenants(id)         ON DELETE CASCADE,
            deal_id       UUID        NOT NULL REFERENCES deals(id)           ON DELETE CASCADE,
            from_stage_id UUID                 REFERENCES pipeline_stages(id) ON DELETE SET NULL,
            to_stage_id   UUID        NOT NULL REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
            changed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_deal_stage_history PRIMARY KEY (id)
        )
    """))

    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_deal_stage_history_tenant_id ON deal_stage_history (tenant_id)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_deal_stage_history_deal_id ON deal_stage_history (deal_id)"
    ))

    _enable_rls(conn, "deal_stage_history")


def downgrade() -> None:
    conn = op.get_bind()

    _disable_rls(conn, "deal_stage_history")
    conn.execute(text("DROP TABLE IF EXISTS deal_stage_history"))

    conn.execute(text("ALTER TABLE deals DROP COLUMN IF EXISTS source"))
    conn.execute(text("ALTER TABLE deals DROP COLUMN IF EXISTS notes"))
    conn.execute(text("ALTER TABLE deals DROP COLUMN IF EXISTS lost_reason"))
    conn.execute(text("ALTER TABLE deals DROP COLUMN IF EXISTS lost_comment"))
