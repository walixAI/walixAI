"""Sprint 13A — tabla deals con RLS.

Revision ID: s6t7u8v9w0x1
Revises: r5s6t7u8v9w0
Create Date: 2026-06-19

Crea la tabla deals: entidad Deal separada de Lead.
El Lead es la persona (contacto); el Deal es la transacción potencial.
Un Lead puede tener múltiples Deals.
RLS sigue el patrón tenant_isolation_* del proyecto.
"""

from alembic import op
from sqlalchemy import text

revision = "s6t7u8v9w0x1"
down_revision = "r5s6t7u8v9w0"
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

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS deals (
            id                  UUID        NOT NULL DEFAULT gen_random_uuid(),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            tenant_id           UUID        NOT NULL REFERENCES tenants(id)         ON DELETE CASCADE,
            lead_id             UUID        NOT NULL REFERENCES leads(id)           ON DELETE CASCADE,
            pipeline_stage_id   UUID        NOT NULL REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
            title               VARCHAR(255) NOT NULL,
            amount              NUMERIC(14,2) NOT NULL DEFAULT 0,
            probability         INTEGER     NOT NULL DEFAULT 0,
            expected_close_date DATE,
            is_won              BOOLEAN     NOT NULL DEFAULT false,
            is_lost             BOOLEAN     NOT NULL DEFAULT false,
            CONSTRAINT pk_deals PRIMARY KEY (id),
            CONSTRAINT ck_deals_probability CHECK (probability BETWEEN 0 AND 100),
            CONSTRAINT ck_deals_amount_non_negative CHECK (amount >= 0)
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_deals_tenant_id ON deals (tenant_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_deals_lead_id   ON deals (lead_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_deals_pipeline_stage_id ON deals (pipeline_stage_id)"))

    _enable_rls(conn, "deals")


def downgrade() -> None:
    conn = op.get_bind()
    _disable_rls(conn, "deals")
    conn.execute(text("DROP TABLE IF EXISTS deals"))
