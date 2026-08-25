"""test_whatsapp_migration.py — Verificación del Prompt Utel #2:
migración de WhatsApp + fix del mensaje de bienvenida hardcodeado.

Cubre SOLO el modo auditoría (solo lectura) de
scripts/admin/migrate_whatsapp_to_utel.py y las funciones puras del fix —
NO corre --execute automáticamente, esa decisión la toma Walix manualmente
después de revisar el output de auditoría.

Verificaciones:
  a) Correr migrate_whatsapp_to_utel.py en modo auditoría (sin --execute)
     contra la BD real y confirmar que NO modificó nada — snapshot de
     (branch_id, wa_phone_number_id, wa_token) de todas las branches antes
     y después debe ser idéntico.
  b) (cubierto por diseño — el test nunca invoca --execute).
  c) Unit tests de _build_ad_lead_welcome_message (app/api/webhooks.py):
     - template=None -> fallback genérico, sin nombre de negocio.
     - template="Hola {name}, bienvenido a Utel" + name="Ana" ->
       "Hola Ana, bienvenido a Utel".
     - template válido + name=None -> usa "amigo/a".
     - regression guard: ningún resultado contiene "Endocrinología" ni
       "Clínica".

Uso:
    .venv/Scripts/python.exe scripts/test_whatsapp_migration.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.api.webhooks import _build_ad_lead_welcome_message
from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch

sys.path.insert(0, str(Path(__file__).resolve().parent / "admin"))
from migrate_whatsapp_to_utel import _audit_mode  # noqa: E402


async def _snapshot() -> dict:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Branch.id, Branch.wa_phone_number_id, Branch.wa_token)
        )).all()
        return {r[0]: (r[1], r[2]) for r in rows}


async def main() -> int:
    print("=" * 70)
    print("  test_whatsapp_migration.py — auditoría (solo lectura) + unit tests")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []

    # ── a) modo auditoría no modifica nada ───────────────────────────────
    before = await _snapshot()
    exit_code = await _audit_mode()
    after = await _snapshot()
    ok_a = before == after and exit_code == 0
    results.append((
        "a. modo auditoría (sin --execute) no modifica ninguna branch, exit_code=0",
        ok_a,
        f"exit_code={exit_code} branches_comparadas={len(before)} idénticas={before == after}",
    ))

    # ── c) unit tests de _build_ad_lead_welcome_message ──────────────────
    fallback = _build_ad_lead_welcome_message(None, None)
    ok_c1 = fallback and "Endocrinología" not in fallback and "Clínica" not in fallback
    results.append((
        "c1. template=None -> fallback genérico, sin nombre de negocio",
        bool(ok_c1),
        f"result={fallback!r}",
    ))

    templated = _build_ad_lead_welcome_message("Ana", "Hola {name}, bienvenido a Utel")
    ok_c2 = templated == "Hola Ana, bienvenido a Utel"
    results.append((
        "c2. template + name='Ana' -> placeholder sustituido correctamente",
        ok_c2,
        f"result={templated!r}",
    ))

    templated_no_name = _build_ad_lead_welcome_message(None, "Hola {name}, bienvenido a Utel")
    ok_c3 = templated_no_name == "Hola amigo/a, bienvenido a Utel"
    results.append((
        "c3. template válido + name=None -> usa 'amigo/a' como fallback de nombre",
        ok_c3,
        f"result={templated_no_name!r}",
    ))

    # Regression guard: ningún resultado, en ningún caso probado, debe
    # contener el hardcodeo original que estamos corrigiendo.
    all_results = [fallback, templated, templated_no_name]
    ok_c4 = all(
        "Endocrinología" not in r and "Clínica" not in r for r in all_results
    )
    results.append((
        "c4. regression guard: ningún resultado contiene 'Endocrinología' ni 'Clínica'",
        ok_c4,
        f"resultados_probados={all_results}",
    ))

    return _report(results)


def _report(results: list[tuple[str, bool, str]]) -> int:
    print()
    all_ok = True
    for label, ok, detail in results:
        tag = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{tag}] {label}\n         {detail}")
    print()
    if all_ok:
        print("✓ Todas las verificaciones pasaron.")
        return 0
    print("✗ Al menos una verificación falló — ver detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
