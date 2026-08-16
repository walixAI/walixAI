"""RLS: cubrir dashboard_panels (deals y deal_stage_history YA la tenían)

Revision ID: k6l7m8n9o0p1
Revises: j5k6l7m8n9o0
Create Date: 2026-08-14

AUDITORÍA previa a este cambio (backend/tests/regression/test_multi_tenancy.py
afirmaba que a `deals`, `deal_stage_history` y `dashboard_panels` "nunca se
les agregó RLS" — verificado contra pg_class.relrowsecurity en la DB real
antes de escribir esta migración, y la afirmación es incorrecta para dos de
las tres tablas):

  - deals              -> relrowsecurity=TRUE, relforcerowsecurity=TRUE.
                          Tiene RLS desde su creación (migración
                          s6t7u8v9w0x1_sprint13a_deals, 2026-06-19), con el
                          mismo patrón tenant_isolation_* de esta migración.
                          NO se toca acá — re-crear las policies fallaría
                          ("policy already exists").
  - deal_stage_history -> relrowsecurity=TRUE, relforcerowsecurity=TRUE.
                          Idem, desde su creación (migración
                          t7u8v9w0x1y2_sprint14a_deal_fields_and_history,
                          2026-06-19). Tiene tenant_id propio (columna
                          directa, NOT NULL) — no hace falta policy vía
                          subquery/JOIN contra deals como se especulaba antes
                          de auditar el schema real.
  - dashboard_panels   -> relrowsecurity=FALSE. Esta es la única tabla que
                          realmente le faltaba RLS: se creó en la migración
                          e40231c281ca (consolidación del dashboard,
                          posterior a h4i5j6k7l8m9_add_row_level_security) y
                          nunca se retrofitteó. Tiene tenant_id propio
                          (columna directa, NOT NULL) — mismo patrón estándar
                          que _DIRECT_TABLES en la migración original.

Por eso esta migración SOLO toca dashboard_panels.
"""

from alembic import op
from sqlalchemy import text

revision = "k6l7m8n9o0p1"
down_revision = "j5k6l7m8n9o0"
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
    _enable_rls(conn, "dashboard_panels")


def downgrade() -> None:
    conn = op.get_bind()
    _disable_rls(conn, "dashboard_panels")
