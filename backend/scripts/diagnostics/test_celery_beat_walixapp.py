"""test_celery_beat_walixapp.py — Diagnóstico de Celery Beat contra walix_app real.

Qué verifica:
    Las 11 tareas de Celery beat de cadencia NO mensual, disparadas
    sincrónicamente (vía Task.apply(), sin pasar por el broker Redis) contra
    producción real bajo el rol walix_app (RLS activo, sin BYPASSRLS). Cubre
    en particular las funciones SECURITY DEFINER cross-tenant de las que
    dependen los barridos periódicos —fn_list_active_branch_tenant_pairs()
    y fn_list_active_alert_rules()— que RLS bloquearía por completo bajo un
    SELECT directo, sin importar qué tenant esté seteado.

    Deliberadamente NO incluye:
      - run_monthly_summaries
      - run_generate_recurring_expenses
    porque corren una vez al mes y dispararlas fuera de horario podría
    duplicar datos si no son idempotentes — se verifican aparte.

Cuándo correrlo:
    Después de cualquier cambio a las policies de RLS, a las funciones
    fn_list_active_* (o cualquier otra SECURITY DEFINER de la que dependan
    los barridos cross-tenant), o a la configuración de Celery/Redis
    (broker, ssl_cert_reqs, rotación de REDIS_URL, etc.).

Última corrida: 2026-08-16 — 11/11 PASS contra producción real (cutover de
RLS walix_app + rotación de REDIS_URL de Upstash).

Uso:
    WALIX_APP_DATABASE_URL="postgresql://walix_app:...@host:puerto/railway" \\
      .venv/Scripts/python.exe scripts/diagnostics/test_celery_beat_walixapp.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_walix_url = os.environ.get("WALIX_APP_DATABASE_URL")
if not _walix_url:
    print("Falta WALIX_APP_DATABASE_URL en el entorno.")
    sys.exit(1)

# Debe estar seteada ANTES de importar cualquier módulo de app.* — Settings()
# se instancia una sola vez al importar app.core.config.
os.environ["DATABASE_URL"] = _walix_url

TASKS = [
    ("app.tasks.agent_tasks", "run_follow_up_all_branches"),
    ("app.tasks.agent_tasks", "run_pipeline_all_branches"),
    ("app.tasks.agent_tasks", "run_config_all_branches"),
    ("app.tasks.agent_tasks", "run_closing_all_branches"),
    ("app.tasks.agent_tasks", "run_reactivation_all_tenants"),
    ("app.tasks.agent_tasks", "run_profile_enrichment_all_tenants"),
    ("app.tasks.agent_tasks", "run_aprendiz_all_tenants"),
    ("app.tasks.metrics_tasks", "aggregate_all_metrics"),
    ("app.tasks.metrics_tasks", "calculate_all_sentiment"),
    ("app.tasks.alerts_tasks", "run_daily_summaries"),
    ("app.tasks.alerts_tasks", "detect_unresponded_leads"),
]

_RED_FLAGS = ("permission denied", "invalid input syntax for type uuid")


def main() -> int:
    import importlib

    # Cada tarea corre en su propio proceso normalmente (worker real, un
    # asyncio.run() por invocación con NullPool — ver worker_process_init en
    # app/celery_app.py). Este script las corre todas en un solo proceso
    # Python, así que replica ese mismo parche acá: sin él, tareas
    # posteriores pueden reusar una conexión pooled atada a un event loop ya
    # cerrado por una tarea anterior ("Event loop is closed" — no es un
    # error de RLS/permisos, es puramente un artefacto de correr muchas
    # tareas secuenciales en un solo proceso).
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
    import app.core.database as _db
    from app.core.config import settings as _settings
    from app.celery_app import _async_url

    _engine = create_async_engine(_async_url(_settings.effective_database_url), poolclass=NullPool)
    _db.AsyncSessionLocal = async_sessionmaker(
        bind=_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False,
    )

    results: list[tuple[str, bool, str]] = []

    for module_name, task_name in TASKS:
        mod = importlib.import_module(module_name)
        task = getattr(mod, task_name)
        label = f"{module_name}.{task_name}"
        try:
            res = task.apply()
            if res.successful():
                detail = str(res.result)
                flagged = any(f in detail.lower() for f in _RED_FLAGS)
                results.append((label, not flagged, detail if flagged else detail[:200]))
            else:
                err = str(res.result)
                flagged = any(f in err.lower() for f in _RED_FLAGS)
                results.append((label, False, f"{'[RED FLAG] ' if flagged else ''}{err[:300]}"))
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            flagged = any(f in err.lower() for f in _RED_FLAGS)
            results.append((label, False, f"{'[RED FLAG] ' if flagged else ''}{err[:300]}"))

    print()
    all_ok = True
    for label, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        all_ok = all_ok and ok
        print(f"  [{status}] {label}\n         {detail}")

    print()
    if all_ok:
        print("Todas las tareas corrieron sin permission denied / invalid uuid syntax.")
        return 0
    print("Al menos una tarea mostró un red flag de RLS/permisos — ver detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
