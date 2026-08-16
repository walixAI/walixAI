"""Enumeración cross-tenant segura: fn_list_active_branch_tenant_pairs

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
Create Date: 2026-08-15

CONTEXTO (distinto del problema de Parte 1): app/tasks/_helpers.py::
get_active_branch_ids() / get_active_tenant_ids() alimentan los barridos
periódicos de Celery beat (follow-up, pipeline, config, closing,
reactivation, profile-enrichment, aprendiz, métricas) — necesitan ver
branches de TODOS los tenants A LA VEZ, por diseño. Esto NO es un caso
"pre-tenant" como login/webhook (una entidad ambigua que se resuelve una
vez y ya): es cross-tenant PERMANENTE. Ningún valor único de
app.current_tenant_id puede satisfacer esta query — set_tenant_context()
no aplica acá en absoluto.

DISEÑO: mismo patrón SECURITY DEFINER que l7m8n9o0p1q2, pero para
enumeración en vez de lookup puntual. Expone SOLO (branch_id, tenant_id) —
nunca wa_token, ai_config, ni ninguna otra columna de branches. Cada
llamador (agent_tasks.py, metrics_tasks.py) sigue necesitando
set_tenant_context(db, tenant_id) DESPUÉS de esto, por cada branch/tenant
que procese individualmente — esta función solo resuelve el paso de
"quién existe", no autoriza a leer más allá de eso.
"""
from alembic import op
from sqlalchemy import text

revision = "m8n9o0p1q2r3"
down_revision = "l7m8n9o0p1q2"
branch_labels = None
depends_on = None

_GRANTEE = "walix_app"


def _role_exists(conn, role: str) -> bool:
    return conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r)"), {"r": role}
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("""
        CREATE FUNCTION fn_list_active_branch_tenant_pairs()
        RETURNS TABLE(branch_id uuid, tenant_id uuid)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT id, tenant_id FROM branches WHERE is_active = TRUE;
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_list_active_branch_tenant_pairs() FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_list_active_branch_tenant_pairs() IS
        'Enumera (branch_id, tenant_id) de TODAS las branches activas, cruzando
        tenants a propósito — usado por los barridos de Celery beat en
        app/tasks/_helpers.py (get_active_branch_ids/get_active_tenant_ids),
        que necesitan ver todos los tenants a la vez y por lo tanto no pueden
        resolverse con set_tenant_context (un solo tenant por sesión).
        SECURITY DEFINER: corre sin RLS sin importar el rol que la invoque.
        Devuelve SOLO id+tenant_id, nunca el resto de la fila de branches.
        GRANT EXECUTE limitado a walix_app — ver migración m8n9o0p1q2r3.'
    """))

    if _role_exists(conn, _GRANTEE):
        conn.execute(text(
            f"GRANT EXECUTE ON FUNCTION fn_list_active_branch_tenant_pairs() TO {_GRANTEE}"
        ))
    else:
        print(
            f"[m8n9o0p1q2r3] AVISO: el rol '{_GRANTEE}' no existe todavía en este entorno — "
            f"la función se creó pero sin GRANT EXECUTE. Correr scripts/setup_db_user.py y "
            f"luego: GRANT EXECUTE ON FUNCTION fn_list_active_branch_tenant_pairs() TO {_GRANTEE};"
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP FUNCTION IF EXISTS fn_list_active_branch_tenant_pairs()"))
