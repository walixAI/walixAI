"""Enumeración cross-tenant segura: fn_list_active_alert_rules

Revision ID: n9o0p1q2r3s4
Revises: m8n9o0p1q2r3
Create Date: 2026-08-15

CONTEXTO: mismo patrón que m8n9o0p1q2r3 (fn_list_active_branch_tenant_pairs),
esta vez para app/tasks/alerts_tasks.py:
  - run_daily_summaries(): necesita AlertRule de TODOS los tenants cuyo
    schedule_hour coincide con la hora actual — barrido cruza-tenant a
    propósito, igual que el de branches.
  - _async_detect_unresponded(): necesita TODAS las AlertRule activas (sin
    filtro de hora) para chequear su ventana de silencio y umbral por
    tenant/branch.

alert_rules SÍ tiene RLS (a diferencia de ai_memory_events/ai_entity_context/
expenses, que no tienen ninguna — hallazgo aparte, documentado para decidir
en un prompt separado, no resuelto acá). Por eso este barrido necesita el
mismo tratamiento SECURITY DEFINER que branches, no un fix de
set_tenant_context (que solo sirve para UN tenant a la vez).

Expone id, branch_id, tenant_id, schedule_hour, silence_start, silence_end,
threshold_hours — los campos que alerts_tasks.py ya lee hoy vía el ORM.
Nunca expone columnas de otras tablas (leads, users, branches) — esas
siguen protegidas por RLS normal una vez que el caller aplica
set_tenant_context con el tenant_id que esta función le da.
"""
from alembic import op
from sqlalchemy import text

revision = "n9o0p1q2r3s4"
down_revision = "m8n9o0p1q2r3"
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
        CREATE FUNCTION fn_list_active_alert_rules()
        RETURNS TABLE(
            id uuid,
            branch_id uuid,
            tenant_id uuid,
            schedule_hour integer,
            silence_start integer,
            silence_end integer,
            threshold_hours integer
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT id, branch_id, tenant_id, schedule_hour, silence_start,
                   silence_end, threshold_hours
            FROM alert_rules
            WHERE is_active = TRUE;
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_list_active_alert_rules() FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_list_active_alert_rules() IS
        'Enumera reglas de alerta activas de TODOS los tenants, cruzando
        tenants a propósito — usado por app/tasks/alerts_tasks.py
        (run_daily_summaries filtra por schedule_hour en Python;
        _async_detect_unresponded usa todas). SECURITY DEFINER: corre sin
        RLS sin importar el rol que la invoque. Devuelve solo las columnas
        de alert_rules que esos callers ya leían vía ORM — nunca datos de
        otras tablas. GRANT EXECUTE limitado a walix_app — ver migración
        n9o0p1q2r3s4.'
    """))

    if _role_exists(conn, _GRANTEE):
        conn.execute(text(
            f"GRANT EXECUTE ON FUNCTION fn_list_active_alert_rules() TO {_GRANTEE}"
        ))
    else:
        print(
            f"[n9o0p1q2r3s4] AVISO: el rol '{_GRANTEE}' no existe todavía en este entorno — "
            f"la función se creó pero sin GRANT EXECUTE. Correr scripts/setup_db_user.py y "
            f"luego: GRANT EXECUTE ON FUNCTION fn_list_active_alert_rules() TO {_GRANTEE};"
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP FUNCTION IF EXISTS fn_list_active_alert_rules()"))
