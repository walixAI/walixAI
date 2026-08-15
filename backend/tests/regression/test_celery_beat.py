"""
Regresión — Celery / jobs periódicos (app/celery_app.py existe: Prompt 2 de
infraestructura urgente ya corrió, reemplazando APScheduler).

Código auditado: app/celery_app.py — `celery_app.conf.beat_schedule` (dict
literal, líneas 78-133). Smoke test: confirma que las tasks de agentes y
métricas están registradas con el nombre de task correcto (formato
"módulo.función"), sin conectarse de verdad al broker de Redis — importar
el módulo Celery no abre conexión (es lazy).
"""
from __future__ import annotations

from app.celery_app import celery_app

# Nombre de la entrada en beat_schedule -> dotted path de la task real,
# tal como está escrito HOY en app/celery_app.py. Si alguna de estas cambia
# de nombre o desaparece, este test debe fallar (es justo lo que se quiere
# detectar como regresión).
_EXPECTED_BEAT_ENTRIES: dict[str, str] = {
    "follow-up-agent-every-2h": "app.tasks.agent_tasks.run_follow_up_all_branches",
    "pipeline-agent-daily": "app.tasks.agent_tasks.run_pipeline_all_branches",
    "config-agent-weekly": "app.tasks.agent_tasks.run_config_all_branches",
    "closing-agent-daily": "app.tasks.agent_tasks.run_closing_all_branches",
    "reactivation-agent-daily": "app.tasks.agent_tasks.run_reactivation_all_tenants",
    "profile-enrichment-every-72h": "app.tasks.agent_tasks.run_profile_enrichment_all_tenants",
    "aggregate-metrics-hourly": "app.tasks.metrics_tasks.aggregate_all_metrics",
    "sentiment-daily": "app.tasks.metrics_tasks.calculate_all_sentiment",
    "daily-summaries-hourly": "app.tasks.alerts_tasks.run_daily_summaries",
    "detect-unresponded-every-30m": "app.tasks.alerts_tasks.detect_unresponded_leads",
    "monthly-summaries": "app.tasks.alerts_tasks.run_monthly_summaries",
    "aprendiz-agent-weekly": "app.tasks.agent_tasks.run_aprendiz_all_tenants",
    "generate-recurring-expenses-monthly": "app.tasks.finance_tasks.run_generate_recurring_expenses",
}


def test_beat_schedule_contains_expected_agent_and_metrics_tasks() -> None:
    schedule = celery_app.conf.beat_schedule
    assert schedule, "celery_app.conf.beat_schedule está vacío — ¿se rompió el registro de tasks?"

    missing = set(_EXPECTED_BEAT_ENTRIES) - set(schedule)
    assert not missing, f"Entradas de beat_schedule faltantes: {sorted(missing)}"

    mismatched = {
        name: (schedule[name]["task"], expected_task)
        for name, expected_task in _EXPECTED_BEAT_ENTRIES.items()
        if schedule[name]["task"] != expected_task
    }
    assert not mismatched, f"Task path distinto al esperado: {mismatched}"


def test_beat_schedule_entries_have_a_schedule_defined() -> None:
    schedule = celery_app.conf.beat_schedule
    for name, entry in schedule.items():
        assert "schedule" in entry and entry["schedule"] is not None, (
            f"Entrada '{name}' de beat_schedule no tiene 'schedule' definido"
        )
