"""test_celery.py — Verifica la migración APScheduler → Celery en Walix.

Checks (a–f) del spec:
  a) beat_schedule tiene los jobs esperados — imprime nombres y horarios
  b) Encola aggregate_all_metrics y espera resultado (máx 30 s)
  c) Tabla failed_tasks existe en BD y es accesible
  d) APScheduler y scheduler.start() NO aparecen en app/main.py
  e) execute_suggestion_task con UUID inexistente maneja error gracefully
  f) PASS/FAIL por cada check con detalle del error si falla

Uso:
  # Con worker corriendo (requerido para b y e async):
  celery -A app.celery_app worker --loglevel=info &
  .venv/bin/python scripts/test_celery.py

  # Solo verificación de configuración, sin worker:
  .venv/bin/python scripts/test_celery.py --no-worker
"""
from __future__ import annotations

import asyncio
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

NEED_WORKER = "--no-worker" not in sys.argv and os.environ.get("APP_ENV") != "test"
ROOT = Path(__file__).resolve().parent.parent

_PASS = "✓ PASS"
_FAIL = "✗ FAIL"
_SKIP = "– SKIP"

failures: list[str] = []


def report(label: str, ok: bool | None, detail: str = "") -> None:
    if ok is None:
        tag = _SKIP
    elif ok:
        tag = _PASS
    else:
        tag = _FAIL
        failures.append(label)
    line = f"  {tag}  {label}"
    if detail:
        line += f"\n         {detail}"
    print(line)


# ─────────────────────────────────────────────────────────────────────────────
# a) beat_schedule tiene los jobs esperados — imprime nombres y horarios
# ─────────────────────────────────────────────────────────────────────────────

def check_a() -> None:
    print("a) Beat schedule ─────────────────────────────────────────")
    from app.celery_app import celery_app

    REQUIRED = {
        "app.tasks.agent_tasks.run_follow_up_all_branches",
        "app.tasks.agent_tasks.run_pipeline_all_branches",
        "app.tasks.agent_tasks.run_config_all_branches",
        "app.tasks.agent_tasks.run_closing_all_branches",
        "app.tasks.agent_tasks.run_reactivation_all_tenants",
        "app.tasks.metrics_tasks.aggregate_all_metrics",
        "app.tasks.metrics_tasks.calculate_all_sentiment",
    }

    schedule = celery_app.conf.beat_schedule
    scheduled_tasks = {entry["task"] for entry in schedule.values()}
    missing = REQUIRED - scheduled_tasks

    print(f"   Entradas totales en beat_schedule: {len(schedule)}")
    for name, entry in sorted(schedule.items()):
        print(f"   • {name}: {entry['schedule']}")

    report(
        f"beat_schedule contiene los {len(REQUIRED)} jobs requeridos",
        len(missing) == 0,
        f"Faltantes: {missing}" if missing else "",
    )


# ─────────────────────────────────────────────────────────────────────────────
# b) Encolar aggregate_all_metrics y esperar resultado (máx 30 s)
# ─────────────────────────────────────────────────────────────────────────────

def check_b() -> None:
    print("\nb) Ejecución de aggregate_all_metrics ────────────────────")
    if not NEED_WORKER:
        # En modo --no-worker/CI no intentamos conectar a Redis
        report("Tarea encolada en Redis", None, "omitido en modo --no-worker/CI")
        report("Resultado de ejecución", None, "omitido en modo --no-worker/CI")
        return

    from app.tasks.metrics_tasks import aggregate_all_metrics

    try:
        task_result = aggregate_all_metrics.delay()
        report(f"Tarea encolada (id={task_result.id[:16]}...)", True)
    except Exception as exc:
        report("Tarea encolada en Redis", False, str(exc))
        return

    print("   Esperando resultado (máx 30 s) — requiere worker activo...")
    deadline = time.time() + 30
    while time.time() < deadline:
        if task_result.ready():
            break
        time.sleep(1)

    if not task_result.ready():
        report(
            "Worker ejecutó la tarea en < 30 s",
            False,
            "Timeout — ¿está corriendo el worker? "
            "(celery -A app.celery_app worker --loglevel=info)",
        )
        return

    if task_result.successful():
        report("Worker ejecutó la tarea exitosamente", True, f"resultado={task_result.result}")
    else:
        report(
            "Worker ejecutó la tarea exitosamente",
            False,
            f"estado={task_result.state}  error={task_result.result}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# c) Tabla failed_tasks existe en BD y COUNT(*) retorna sin error
# ─────────────────────────────────────────────────────────────────────────────

def check_c() -> None:
    print("\nc) Tabla failed_tasks en BD ─────────────────────────────")

    async def _query() -> int:
        from sqlalchemy import text
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT COUNT(*) FROM failed_tasks"))
            return result.scalar_one()

    try:
        count = asyncio.run(_query())
        report(
            "Tabla failed_tasks existe y es accesible (COUNT=0 esperado en tabla vacía)",
            True,
            f"filas actuales: {count}",
        )
    except Exception as exc:
        report(
            "Tabla failed_tasks existe y es accesible",
            False,
            f"{exc} — ¿se ejecutó 'alembic upgrade head'?",
        )


# ─────────────────────────────────────────────────────────────────────────────
# d) APScheduler y scheduler.start() NO están en app/main.py
# ─────────────────────────────────────────────────────────────────────────────

def check_d() -> None:
    print("\nd) APScheduler eliminado de app/main.py ─────────────────")
    main_path = ROOT / "app" / "main.py"
    content = main_path.read_text()

    has_apscheduler = "APScheduler" in content or "apscheduler" in content
    has_start = "scheduler.start()" in content

    report("Sin import/referencia a APScheduler en main.py", not has_apscheduler)
    report("Sin scheduler.start() en main.py", not has_start)


# ─────────────────────────────────────────────────────────────────────────────
# e) execute_suggestion_task con UUID inexistente — error graceful, no crash
# ─────────────────────────────────────────────────────────────────────────────

def check_e() -> None:
    print("\ne) execute_suggestion_task con UUID falso ───────────────")
    from app.tasks.agent_tasks import execute_suggestion_task

    fake_id = str(uuid.uuid4())

    if NEED_WORKER:
        # Ejecución real en el worker
        try:
            r = execute_suggestion_task.delay(fake_id, str(uuid.uuid4()))
            report(f"Tarea encolada (id={r.id[:16]}...)", True)
        except Exception as exc:
            report("Tarea encolada con UUID falso", False, str(exc))
            return

        print("   Esperando resultado (máx 15 s)...")
        deadline = time.time() + 15
        while time.time() < deadline and not r.ready():
            time.sleep(1)

        if not r.ready():
            report("Worker procesó la tarea en < 15 s", False, "Timeout")
            return

        # Debe fallar (UUID no existe) — eso es correcto para un DLQ test
        # El worker no debe haber crasheado; solo debe haber marcado la tarea FAILURE
        report(
            "Worker manejó el error gracefully (FAILURE, sin crash del proceso)",
            r.state == "FAILURE",
            f"estado={r.state}",
        )
    else:
        # Sin worker: ejecutar síncronamente para verificar manejo de excepciones
        # apply() corre la task en el proceso actual, sin broker. Por default
        # (task_eager_propagates no está seteado en celery_app.conf) apply()
        # NUNCA re-lanza la excepción al caller — la captura y la guarda en
        # el EagerResult como estado FAILURE, igual que con un worker real.
        # Un try/except acá nunca vería la excepción; hay que chequear el
        # resultado, no esperar que .apply() explote.
        r = execute_suggestion_task.apply(args=[fake_id, str(uuid.uuid4())])
        report(
            "Error manejado gracefully (FAILURE, sin crash del proceso)",
            r.state == "FAILURE",
            f"estado={r.state}" + (f" — {r.result}" if r.state == "FAILURE" else ""),
        )


# ─────────────────────────────────────────────────────────────────────────────
# f) Resumen PASS/FAIL — impreso por report() durante cada check
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    mode = "con worker" if NEED_WORKER else "sin worker (--no-worker)"
    print(f"\n{'═' * 58}")
    print(f"  WALIX — Verificación Celery ({mode})")
    print(f"{'═' * 58}\n")

    check_a()
    check_b()
    check_c()
    check_d()
    check_e()

    print(f"\n{'─' * 58}")
    if not failures:
        print(f"  {_PASS}  Todas las verificaciones pasaron.\n")
    else:
        print(f"  {_FAIL}  {len(failures)} check(s) fallaron:")
        for f in failures:
            print(f"    • {f}")
        print()

    print("Próximos pasos en Railway:")
    print("  1. Crear servicio 'walix-worker'")
    print("     Start Command: celery -A app.celery_app worker --loglevel=info --concurrency=2")
    print("  2. Crear servicio 'walix-beat'")
    print("     Start Command: celery -A app.celery_app beat --loglevel=info")
    print("  3. Ambos servicios: mismas env vars que el servicio web")
    print("  4. Solo un proceso beat aunque haya múltiples workers")
    print()
    print("Flower (monitoreo):")
    print("  celery -A app.celery_app flower --port=5555")
    print("  http://localhost:5555\n")

    return len(failures)


if __name__ == "__main__":
    sys.exit(main())
