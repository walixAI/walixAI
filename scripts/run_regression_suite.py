"""Orquestador de la suite de regresión general de Walix.

Corre, EN ORDEN, y acumula resultado sin abortar entre pasos:
  1. pytest backend/tests/regression/ -v --tb=short          (cwd=backend/)
  2. npx playwright test e2e/regression/ --reporter=list      (cwd=frontend/)
  3. python scripts/test_webhook.py                           (cwd=backend/, SIEMPRE corre,
     incluso si 1 o 2 fallaron — es el ancla que confirma que la clínica sigue
     funcionando pase lo que pase)

Distingue FAILs "conocidos y documentados" de FAILs nuevos:
  - El único FAIL conocido hoy es
    test_rls_bypass_leaks_cross_tenant_lead_when_querying_unfiltered
    (rol `postgres` de Railway con rolbypassrls=TRUE — ver el docstring de
    backend/tests/regression/test_multi_tenancy.py líneas 20-43). Esperado
    que falle en este entorno; no bloquea el exit code.
  - Cualquier otro FAIL (en pytest, en Playwright, o en test_webhook.py) es
    "nuevo" y hace que el script termine con sys.exit(1).

Requiere backend (uvicorn) y frontend (vite) corriendo en background antes
de invocar este script — ver docstring de scripts/run_regression_suite.py /
el prompt que lo generó para el orden de arranque completo.

Uso:
    python scripts/run_regression_suite.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

# La consola de Windows suele usar cp1252 por default, que no soporta los
# caracteres unicode (→, ✓, ✗, tildes) que usa este script y la salida de
# pytest/Playwright/test_webhook.py. Forzar UTF-8 evita un UnicodeEncodeError
# a mitad de la suite.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Sustrings de nodeid/nombre de test que cuentan como FAIL conocido y documentado.
_KNOWN_BACKEND_FAILURES = {
    "test_rls_bypass_leaks_cross_tenant_lead_when_querying_unfiltered",
}

_KNOWN_FAILURES_NOTE = (
    "  - test_rls_bypass_leaks_cross_tenant_lead_when_querying_unfiltered\n"
    "    (rol postgres con rolbypassrls=TRUE, ver test_multi_tenancy.py líneas 20-43)"
)


def _backend_python() -> str:
    """Prefiere el intérprete del venv de backend/ si existe; si no, el actual."""
    for candidate in (BACKEND / ".venv" / "Scripts" / "python.exe", BACKEND / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


class StepResult:
    def __init__(self, name: str) -> None:
        self.name = name
        self.exit_code: int | None = None
        self.stdout = ""
        self.stderr = ""
        self.ran = False

    @property
    def ok(self) -> bool:
        return self.ran and self.exit_code == 0


def _run(name: str, args: list[str], cwd: Path) -> StepResult:
    result = StepResult(name)
    print(f"\n{'=' * 70}\n→ {name}\n  {' '.join(args)}  (cwd={cwd})\n{'=' * 70}")
    try:
        proc = subprocess.run(
            args, cwd=str(cwd), capture_output=True, shell=False,
            encoding="utf-8", errors="replace",
        )
        result.ran = True
        result.exit_code = proc.returncode
        result.stdout = proc.stdout
        result.stderr = proc.stderr
    except FileNotFoundError as e:
        result.ran = True
        result.exit_code = 127
        result.stderr = f"No se pudo ejecutar el comando: {e}"

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result


# ── 1. Backend pytest ───────────────────────────────────────────────────────

def run_backend_tests() -> tuple[StepResult, list[str], list[str]]:
    """Retorna (result, tests_fallidos, tests_fallidos_no_documentados)."""
    result = _run(
        "backend/pytest",
        [_backend_python(), "-m", "pytest", "tests/regression/", "-v", "--tb=short"],
        BACKEND,
    )
    # pytest.ini trae `-q` en addopts, que se cancela con el `-v` de arriba
    # (la verbosidad de pytest es aditiva, no "el último gana") — el resultado
    # es el reporte compacto por punto, no líneas "nodeid PASSED/FAILED". Lo
    # único que aparece siempre, sin importar la verbosidad efectiva, es la
    # sección "short test summary info" con formato "FAILED nodeid" (FAILED
    # primero). Por eso el match es sobre ESE formato, no el verboso.
    failed_nodeids = re.findall(r"^FAILED\s+(\S+)", result.stdout, re.MULTILINE)
    new_failures = [
        nid for nid in failed_nodeids
        if not any(known in nid for known in _KNOWN_BACKEND_FAILURES)
    ]
    return result, failed_nodeids, new_failures


# ── 2. Frontend Playwright ──────────────────────────────────────────────────

def run_frontend_tests() -> StepResult:
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    return _run(
        "frontend/playwright",
        # --workers=2: el backend de este entorno apunta a la DB real de
        # Railway (vía proxy público, no localhost) — con el default de 4+
        # workers en paralelo se observó latencia/timeouts intermitentes de
        # red bajo carga concurrente. 2 workers es un balance razonable entre
        # velocidad y estabilidad contra un backend compartido real.
        [npx, "playwright", "test", "e2e/regression/", "--reporter=list", "--workers=2"],
        FRONTEND,
    )


# ── 3. test_webhook.py (ancla) ──────────────────────────────────────────────

def run_webhook_anchor() -> StepResult:
    return _run("test_webhook.py", [_backend_python(), "scripts/test_webhook.py"], BACKEND)


# ── Resumen ──────────────────────────────────────────────────────────────────

def _status_label(ok: bool, detail: str = "") -> str:
    base = "PASS" if ok else "FAIL"
    return f"{base} ({detail})" if detail and not ok else base


def main() -> int:
    backend_result, backend_failed, backend_new_failures = run_backend_tests()
    frontend_result = run_frontend_tests()
    webhook_result = run_webhook_anchor()

    backend_only_known_fail = bool(backend_failed) and not backend_new_failures
    backend_ok_for_exit = (not backend_failed) or backend_only_known_fail

    if backend_failed:
        detail = f"{len(backend_failed)} test(s) fallido(s)"
        if backend_new_failures:
            detail += f", {len(backend_new_failures)} NO documentado(s)"
        else:
            detail += " — todos documentados, ver bloque de abajo"
        backend_line = _status_label(False, detail)
    else:
        backend_line = "PASS"

    frontend_line = _status_label(frontend_result.ok)
    webhook_line = _status_label(webhook_result.ok)

    print("\n=== RESUMEN SUITE DE REGRESIÓN ===")
    print(f"backend/pytest       : {backend_line}")
    print(f"frontend/playwright  : {frontend_line}")
    print(f"test_webhook.py      : {webhook_line}")
    print("-----------------------------------")
    print("FAILS CONOCIDOS Y DOCUMENTADOS (no bloqueantes para este resumen):")
    print(_KNOWN_FAILURES_NOTE)

    any_new_failure = bool(backend_new_failures) or not frontend_result.ok or not webhook_result.ok

    if any_new_failure:
        print("\n✗ Hay al menos un FAIL nuevo NO documentado — ver detalle arriba.")
        return 1

    if backend_only_known_fail:
        print("\n✓ Único FAIL presente es el de RLS ya documentado — exit 0.")
    else:
        print("\n✓ Suite completa sin FAILs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
