"""Pipeline Oportunidades — opportunities + stage_history + activities.

Revision ID: r5s6t7u8v9w0
Revises: q3r4s5t6u7v8
Create Date: 2026-06-18

Cambios:
  1. ADD COLUMN probability_default SMALLINT en pipeline_stages (idempotente).
  2. CREATE TABLE opportunities con índices compuestos y RLS.
  3. CREATE TABLE opportunity_stage_history con RLS.
  4. CREATE TABLE opportunity_activities con RLS.

RLS: replica el patrón de h4i5j6k7l8m9 (4 políticas por tabla, tenant_id directo).
No toca tenants existentes ni pipeline_stages de la clínica beta.
"""

from alembic import op
from sqlalchemy import text

revision = "r5s6t7u8v9w0"
down_revision = "q3r4s5t6u7v8"
branch_labels = None
depends_on = None

_TENANT_EXPR = "current_setting('app.current_tenant_id', TRUE)::uuid"

# ── RLS helpers (mismo patrón que h4i5j6k7l8m9) ──────────────────────────────


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


# ── Upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:
    conn = op.get_bind()

    # 1. pipeline_stages: añadir probability_default si no existe
    conn.execute(text(
        "ALTER TABLE pipeline_stages"
        "  ADD COLUMN IF NOT EXISTS probability_default SMALLINT"
    ))

    # 2. opportunities
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id              UUID        NOT NULL DEFAULT gen_random_uuid(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            tenant_id       UUID        NOT NULL REFERENCES tenants(id)         ON DELETE CASCADE,
            branch_id       UUID        NOT NULL REFERENCES branches(id)        ON DELETE CASCADE,
            lead_id         UUID                 REFERENCES leads(id)           ON DELETE SET NULL,
            stage_id        UUID                 REFERENCES pipeline_stages(id) ON DELETE SET NULL,
            assigned_to     UUID                 REFERENCES users(id)           ON DELETE SET NULL,
            title           VARCHAR(255) NOT NULL,
            amount          NUMERIC(14,2),
            currency        VARCHAR(3)  NOT NULL DEFAULT 'MXN',
            probability     SMALLINT,
            close_date      DATE,
            source          VARCHAR(20),
            status          VARCHAR(10) NOT NULL DEFAULT 'open',
            won_at          TIMESTAMPTZ,
            lost_at         TIMESTAMPTZ,
            lost_reason     TEXT,
            stage_entered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_activity_at TIMESTAMPTZ,
            ai_suggestion   TEXT,
            ai_suggestion_urgency VARCHAR(10),
            urgency_score   SMALLINT,
            notes           TEXT,
            deleted_at      TIMESTAMPTZ,
            PRIMARY KEY (id)
        )
    """))

    # Simple indices
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opportunities_tenant_id   ON opportunities (tenant_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opportunities_branch_id   ON opportunities (branch_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opportunities_lead_id     ON opportunities (lead_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opportunities_stage_id    ON opportunities (stage_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opportunities_deleted_at  ON opportunities (deleted_at)"))
    # Composite indices
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opp_tenant_branch_stage   ON opportunities (tenant_id, branch_id, stage_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opp_tenant_status         ON opportunities (tenant_id, status)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opp_tenant_close_date     ON opportunities (tenant_id, close_date)"))

    _enable_rls(conn, "opportunities")

    # 3. opportunity_stage_history
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS opportunity_stage_history (
            id              UUID        NOT NULL DEFAULT gen_random_uuid(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            tenant_id       UUID        NOT NULL REFERENCES tenants(id)         ON DELETE CASCADE,
            opportunity_id  UUID        NOT NULL REFERENCES opportunities(id)   ON DELETE CASCADE,
            from_stage_id   UUID                 REFERENCES pipeline_stages(id) ON DELETE SET NULL,
            to_stage_id     UUID        NOT NULL REFERENCES pipeline_stages(id) ON DELETE CASCADE,
            changed_by      UUID                 REFERENCES users(id)           ON DELETE SET NULL,
            PRIMARY KEY (id)
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opp_stage_history_tenant_id      ON opportunity_stage_history (tenant_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opp_stage_history_opportunity_id ON opportunity_stage_history (opportunity_id)"))

    _enable_rls(conn, "opportunity_stage_history")

    # 4. opportunity_activities
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS opportunity_activities (
            id              UUID        NOT NULL DEFAULT gen_random_uuid(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            tenant_id       UUID        NOT NULL REFERENCES tenants(id)       ON DELETE CASCADE,
            opportunity_id  UUID        NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            type            VARCHAR(20) NOT NULL,
            description     TEXT,
            created_by      UUID                 REFERENCES users(id)         ON DELETE SET NULL,
            PRIMARY KEY (id)
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opp_activities_tenant_id      ON opportunity_activities (tenant_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opp_activities_opportunity_id ON opportunity_activities (opportunity_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_opp_activities_type           ON opportunity_activities (type)"))

    _enable_rls(conn, "opportunity_activities")


# ── Downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    conn = op.get_bind()

    _disable_rls(conn, "opportunity_activities")
    _disable_rls(conn, "opportunity_stage_history")
    _disable_rls(conn, "opportunities")

    conn.execute(text("DROP TABLE IF EXISTS opportunity_activities"))
    conn.execute(text("DROP TABLE IF EXISTS opportunity_stage_history"))
    conn.execute(text("DROP TABLE IF EXISTS opportunities"))

    conn.execute(text(
        "ALTER TABLE pipeline_stages DROP COLUMN IF EXISTS probability_default"
    ))
