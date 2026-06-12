"""test_celery.py — Verifica la configuración de Celery + Redis para Walix.

Comprueba:
  a) Conexión a Redis y encolado de tarea
  b) Resultado disponible en Redis (requiere worker en ejecución)
  c) Schedule de Beat configurado correctamente
  d) Tarea DLQ registrada
  e) Re-encolado con task_acks_late (verificación de configuración)

Uso:
    # Con worker en ejecución:
    celery -A app.celery_app worker --loglevel=info &
    python scripts/test_celery.py

    # Sin worker (solo verifica configuración):
    python scripts/test_celery.py --no-worker
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WORKER_REQUIRED = "--no-worker" not in sys.argv

_PASS = "✅ PASS"
_FAIL = "❌ FAIL"


def result(label: str, ok: bool, detail: str = "") -> None:
    tag = _PASS if ok else _FAIL
    line = f"  {tag}  {label}"
    if detail:
        line += f"\n         {detail}"
    print(line)


def main() -> int:
    print("\n══════════════════════════════════════════════════════")
    print("  WALIX — Verificación Celery + Redis")
    print("══════════════════════════════════════════════════════\n")

    failures = 0

    # ── a) Conexión a Redis ───────────────────────────────────────────────────
    print("→ Verificando conexión a Redis...\n")
    try:
        from app.celery_app import celery_app
        conn = celery_app.connection()
        conn.ensure_connection(max_retries=3)
        conn.close()
        result("Conexión a Redis (broker) establecida", True)
    except Exception as exc:
        result("Conexión a Redis (broker) establecida", False, str(exc))
        failures += 1
        print("\n❌  No se puede conectar a Redis. Verifica REDIS_URL en .env.\n")
        return failures

    # ── b) Encolado y ejecución (si hay worker) ───────────────────────────────
    print()
    from app.tasks.agent_tasks import run_follow_up_all_branches

    try:
        task_result = run_follow_up_all_branches.delay()
        result(
            f"Tarea encolada correctamente (task_id={task_result.id[:16]}...)",
            True,
        )
    except Exception as exc:
        result("Tarea encolada correctamente", False, str(exc))
        failures += 1
        task_result = None

    if task_result and WORKER_REQUIRED:
        print("  Esperando resultado (máx 30 s, requiere worker en ejecución)...")
        try:
            value = task_result.get(timeout=30)
            result(
                "Worker ejecutó la tarea y devolvió resultado",
                True,
                f"resultado={value}",
            )
        except Exception as exc:
            result(
                "Worker ejecutó la tarea y devolvió resultado",
                False,
                f"{exc} — ¿está corriendo el worker? (celery -A app.celery_app worker)",
            )
            failures += 1
    elif task_result:
        result(
            "Verificación de ejecución omitida (--no-worker)",
            True,
            f"task_id={task_result.id} encolado en Redis",
        )

    # ── c) Beat schedule configurado ─────────────────────────────────────────
    print()
    print("→ Verificando Beat schedule...\n")
    from app.celery_app import celery_app as _app

    expected_tasks = {
        "app.tasks.agent_tasks.run_follow_up_all_branches",
        "app.tasks.agent_tasks.run_pipeline_all_branches",
        "app.tasks.agent_tasks.run_config_all_branches",
        "app.tasks.agent_tasks.run_reactivation_all_tenants",
        "app.tasks.agent_tasks.run_profile_enrichment_all_tenants",
        "app.tasks.metrics_tasks.aggregate_all_metrics",
        "app.tasks.metrics_tasks.calculate_all_sentiment",
        "app.tasks.alerts_tasks.run_daily_summaries",
        "app.tasks.alerts_tasks.detect_unresponded_leads",
        "app.tasks.alerts_tasks.run_monthly_summaries",
    }

    scheduled_tasks = {
        entry["task"]
        for entry in _app.conf.beat_schedule.values()
    }

    missing = expected_tasks - scheduled_tasks
    result(
        f"Beat schedule contiene las {len(expected_tasks)} tareas esperadas",
        len(missing) == 0,
        f"Faltantes: {missing}" if missing else "",
    )
    if missing:
        failures += 1

    # ── d) Tarea DLQ registrada ───────────────────────────────────────────────
    print()
    dlq_name = "app.tasks.dlq_handler.handle_failed_task"
    dlq_registered = dlq_name in _app.tasks
    result(
        "Tarea DLQ registrada en el registro Celery",
        dlq_registered,
        f"Busca '{dlq_name}'" if not dlq_registered else "",
    )
    if not dlq_registered:
        failures += 1

    # ── e) Configuración task_acks_late ───────────────────────────────────────
    print()
    acks_late = _app.conf.task_acks_late is True
    reject_on_lost = _app.conf.task_reject_on_worker_lost is True
    result(
        "task_acks_late=True (no pierde tareas en reinicio)",
        acks_late,
    )
    result(
        "task_reject_on_worker_lost=True (re-encola si el worker muere)",
        reject_on_lost,
    )
    if not acks_late:
        failures += 1
    if not reject_on_lost:
        failures += 1

    # ── Resumen ───────────────────────────────────────────────────────────────
    print()
    if failures == 0:
        print("✅  Todas las verificaciones pasaron — Celery está configurado correctamente.\n")
    else:
        print(f"❌  {failures} verificación(es) fallaron.\n")

    print("Próximos pasos en Railway:")
    print("  1. Añadir servicio 'worker': imagen del backend, comando del Procfile")
    print("  2. Añadir servicio 'beat':   imagen del backend, comando del Procfile")
    print("  3. Ambos servicios necesitan las mismas variables de entorno que 'web'\n")

    return failures


if __name__ == "__main__":
    sys.exit(main())
