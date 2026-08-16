"""
Regresión — Grupo C de RLS Parte 2: fn_list_active_alert_rules + alert_generator.

Código auditado:
  - app/tasks/_helpers.py::get_active_alert_rules() usa
    fn_list_active_alert_rules() (SECURITY DEFINER, migración n9o0p1q2r3s4) —
    mismo motivo que fn_list_active_branch_tenant_pairs: alert_rules SÍ tiene
    RLS, y run_daily_summaries/_async_detect_unresponded necesitan verlas de
    TODOS los tenants a la vez.
  - app/services/alert_generator.py::send_daily_summary/send_no_response_alert/
    send_monthly_summary ahora reciben tenant_id explícito y llaman
    set_tenant_context() antes de la primera query.

Mismo patrón de test que test_agents_rls.py: se llama la función SQL
directamente en la sesión impersonada (no el wrapper Python, que abre su
propia conexión — ver esa nota en test_agents_rls.py), y se prueban las
queries iniciales de alert_generator armando datos para que el early-return
natural dispare antes de necesitar un mock de Anthropic/WhatsApp.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertRule
from app.models.tenant import Branch
from tests.regression.conftest import impersonate_walix_app_or_skip


async def test_fn_list_active_alert_rules_sees_all_tenants_under_real_rls(
    db: AsyncSession, tenant, branch: Branch,
) -> None:
    rule = AlertRule(
        branch_id=branch.id, tenant_id=tenant.id, alert_type="daily_summary",
        is_active=True, schedule_hour=14,
    )
    db.add(rule)
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    rows = (await db.execute(text("SELECT id, branch_id, tenant_id, schedule_hour FROM fn_list_active_alert_rules()"))).fetchall()
    matches = [r for r in rows if r.id == rule.id]
    assert len(matches) == 1
    assert matches[0].branch_id == branch.id
    assert matches[0].tenant_id == tenant.id
    assert matches[0].schedule_hour == 14

    # NOTA: send_daily_summary/send_no_response_alert/send_monthly_summary
    # NO se prueban acá directamente — cada uno abre su PROPIA
    # AsyncSessionLocal() (otra conexión real), así que no heredarían la
    # impersonación de este test ni verían los datos del fixture (sin commit
    # todavía, conexión/snapshot distinto) — mismo motivo documentado en
    # test_agents_rls.py. Quedan cubiertos por la verificación manual de
    # Paso 3 contra un servidor real con DATABASE_URL apuntando a walix_app.
