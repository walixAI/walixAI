"""migrate_whatsapp_to_utel.py — Migra el número de WhatsApp Business conectado
(hoy en la branch de la clínica, tenant de pruebas sin marca real en Meta) a la
branch principal del tenant "Universidad Utel" (creado por
scripts/admin/create_tenant_utel.py, Prompt Utel #1).

Es puramente un cambio de configuración en la BD de Walix (wa_phone_number_id +
wa_token en la fila de branches) — no toca nada en Meta Business Manager. El
número es de pruebas, sin perfil de negocio verificado a nombre de la clínica.

Dos modos:

  MODO AUDITORÍA (default, SIN --execute) — solo lectura, ningún efecto
  secundario, se puede correr las veces que haga falta:
    .venv/Scripts/python.exe scripts/admin/migrate_whatsapp_to_utel.py

  MODO EJECUCIÓN (--execute) — aplica el cambio en una transacción, después de
  repetir exactamente las mismas verificaciones del modo auditoría:
    .venv/Scripts/python.exe scripts/admin/migrate_whatsapp_to_utel.py --execute

--origin-branch-id=<uuid> (opcional, ambos modos): desambigua manualmente
cuál branch es la fuente cuando el paso (a) encuentra MÁS DE UNA branch con
wa_phone_number_id conectado — el default (sin este flag) sigue siendo
ABORTAR en ese caso, esto no debilita esa protección para corridas futuras,
solo permite que un operador que ya identificó la branch correcta lo diga
explícitamente en vez de que el script adivine.

wa_token se guarda hoy en texto plano en BD (confirmado leyendo
app/api/branches.py::save_meta_config, línea ~348 — "stored as-is") — el
comentario de app/models/meta_ads.py que dice "Encrypted at the application
layer" está desactualizado. Por eso este script solo copia el string, sin
encriptar/desencriptar nada. Ese hallazgo (falta de encriptación real) queda
fuera de alcance de este prompt, es un hallazgo aparte para el backlog.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch, Tenant
from app.services.tenant_setup import _find_principal_branch

UTEL_EMAIL = "admin@utel.walix.mx"


def _mask_token(token: str | None) -> str:
    if not token:
        return "None"
    return f"{token[:6]}..."


@dataclass
class _AuditResult:
    status: str  # "ready" | "already_migrated" | "nothing_connected" | "error"
    message: str
    origin_branch: Branch | None = None
    origin_tenant: Tenant | None = None
    utel_tenant: Tenant | None = None
    utel_branch: Branch | None = None
    origin_ambiguity_note: str | None = None


async def _run_audit(db, origin_branch_id: uuid.UUID | None = None) -> _AuditResult:
    """Repite las verificaciones (a)-(c) del modo auditoría. No modifica nada."""
    utel_tenant = (await db.execute(
        select(Tenant).where(Tenant.email == UTEL_EMAIL)
    )).scalar_one_or_none()
    if utel_tenant is None:
        return _AuditResult(
            status="error",
            message=(
                f"No existe ningún tenant con email {UTEL_EMAIL!r}. "
                "Correr primero scripts/admin/create_tenant_utel.py (Prompt Utel #1)."
            ),
        )

    utel_branch = await _find_principal_branch(utel_tenant.id, db)
    if utel_branch is None:
        return _AuditResult(
            status="error",
            message=f"El tenant Utel (id={utel_tenant.id}) no tiene ninguna branch activa.",
        )

    # (a) branches con wa_phone_number_id conectado, con su tenant
    connected_rows = (await db.execute(
        select(Branch, Tenant)
        .join(Tenant, Tenant.id == Branch.tenant_id)
        .where(Branch.wa_phone_number_id.isnot(None))
    )).all()

    if not connected_rows:
        return _AuditResult(
            status="nothing_connected",
            message="No hay ninguna branch con WhatsApp conectado en todo el sistema — nada que migrar.",
            utel_tenant=utel_tenant,
            utel_branch=utel_branch,
        )

    # (c) más de una branch con número conectado -> abortar, decisión manual —
    # salvo que el operador ya haya identificado la branch correcta vía
    # --origin-branch-id (ver docstring del módulo).
    if len(connected_rows) > 1:
        lines = "\n".join(
            f"    - tenant={t.name!r} branch={b.name!r} (branch_id={b.id}) "
            f"wa_phone_number_id={b.wa_phone_number_id} wa_token={_mask_token(b.wa_token)}"
            for b, t in connected_rows
        )
        if origin_branch_id is None:
            return _AuditResult(
                status="error",
                message=(
                    f"Se encontraron {len(connected_rows)} branches con número conectado — "
                    "el script asume que hay exactamente una fuente. Decisión manual requerida, "
                    "no se continúa (o volver a correr con --origin-branch-id=<uuid> si ya se "
                    "identificó cuál es la correcta):\n" + lines
                ),
            )
        matches = [(b, t) for b, t in connected_rows if b.id == origin_branch_id]
        if not matches:
            return _AuditResult(
                status="error",
                message=(
                    f"--origin-branch-id={origin_branch_id} no coincide con ninguna de las "
                    f"{len(connected_rows)} branches con número conectado:\n" + lines
                ),
            )
        origin_branch, origin_tenant = matches[0]
        others = "\n".join(
            f"    - tenant={t.name!r} branch={b.name!r} (branch_id={b.id}) "
            f"wa_phone_number_id={b.wa_phone_number_id} wa_token={_mask_token(b.wa_token)} "
            f"(ignorada — no seleccionada)"
            for b, t in connected_rows
            if b.id != origin_branch_id
        )
        origin_ambiguity_note = (
            f"Se encontraron {len(connected_rows)} branches con número conectado; se usó "
            f"--origin-branch-id={origin_branch_id} para desambiguar. Otras branches "
            f"conectadas, ignoradas a propósito:\n{others}"
        )
    else:
        origin_branch, origin_tenant = connected_rows[0]
        origin_ambiguity_note = None

    # Caso: ya migrado — la única branch conectada es la de Utel.
    if origin_branch.id == utel_branch.id:
        return _AuditResult(
            status="already_migrated",
            message=(
                f"Utel ya es el destino conectado (wa_phone_number_id="
                f"{origin_branch.wa_phone_number_id}, wa_token={_mask_token(origin_branch.wa_token)}). "
                "No hay ninguna otra branch con número — la migración ya se aplicó, nada pendiente."
            ),
            origin_branch=origin_branch,
            origin_tenant=origin_tenant,
            utel_tenant=utel_tenant,
            utel_branch=utel_branch,
        )

    # (b) la branch principal de Utel debe estar limpia (None/None) hoy —
    # si no, alguien ya conectó algo ahí que no es el resultado de esta
    # migración: no hay que sobreescribirlo.
    if utel_branch.wa_phone_number_id is not None or utel_branch.wa_token is not None:
        return _AuditResult(
            status="error",
            message=(
                f"La branch principal de Utel (id={utel_branch.id}) ya tiene un WhatsApp "
                f"conectado (wa_phone_number_id={utel_branch.wa_phone_number_id}, "
                f"wa_token={_mask_token(utel_branch.wa_token)}) que NO coincide con el origen "
                f"detectado (id={origin_branch.id}). No se sobreescribe una conexión existente "
                "— revisar manualmente."
            ),
        )

    return _AuditResult(
        status="ready",
        message="Auditoría OK — listo para migrar.",
        origin_branch=origin_branch,
        origin_tenant=origin_tenant,
        utel_tenant=utel_tenant,
        utel_branch=utel_branch,
        origin_ambiguity_note=origin_ambiguity_note,
    )


def _print_audit_report(result: _AuditResult) -> None:
    print("=" * 70)
    print("  migrate_whatsapp_to_utel.py — AUDITORÍA (ningún cambio aplicado)")
    print("=" * 70)
    print()
    if result.status == "ready":
        ob, ot, ub, ut = result.origin_branch, result.origin_tenant, result.utel_branch, result.utel_tenant
        if result.origin_ambiguity_note:
            print(result.origin_ambiguity_note)
            print()
        print(f"Origen detectado:  tenant={ot.name!r}, branch={ob.name!r} (id={ob.id})")
        print(f"                   wa_phone_number_id={ob.wa_phone_number_id}")
        print(f"                   wa_token={_mask_token(ob.wa_token)}")
        print()
        print(f"Destino:           tenant={ut.name!r}, branch={ub.name!r} (id={ub.id})")
        print("                   actualmente sin WhatsApp conectado (wa_phone_number_id=None, wa_token=None)")
        print()
        print("Para ejecutar la migración:")
        print("  python scripts/admin/migrate_whatsapp_to_utel.py --execute")
    else:
        print(result.message)
    print()


async def _audit_mode(origin_branch_id: uuid.UUID | None = None) -> int:
    async with AsyncSessionLocal() as db:
        result = await _run_audit(db, origin_branch_id)
    _print_audit_report(result)
    # (e) el modo auditoría siempre sale con código 0 — nunca pide confirmación
    # interactiva, --execute ES la confirmación.
    return 0


async def _execute_mode(origin_branch_id: uuid.UUID | None = None) -> int:
    print("=" * 70)
    print("  migrate_whatsapp_to_utel.py — MODO EJECUCIÓN (--execute)")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        result = await _run_audit(db, origin_branch_id)
        if result.origin_ambiguity_note:
            print(result.origin_ambiguity_note)
            print()

        if result.status == "already_migrated":
            print("Nada que hacer — " + result.message)
            return 0

        if result.status != "ready":
            print("ABORTADO — el estado actual no coincide con lo esperado para migrar:")
            print(result.message)
            return 1

        origin_branch = result.origin_branch
        utel_branch = result.utel_branch
        moved_number = origin_branch.wa_phone_number_id

        utel_branch.wa_phone_number_id = origin_branch.wa_phone_number_id
        utel_branch.wa_token = origin_branch.wa_token
        origin_branch.wa_phone_number_id = None
        origin_branch.wa_token = None
        await db.commit()

        print("✓ Migración aplicada.")
        print(f"  origen  branch_id={origin_branch.id} ({result.origin_tenant.name}) -> desconectado")
        print(f"  destino branch_id={utel_branch.id} ({result.utel_tenant.name}) -> conectado")
        print(f"  wa_phone_number_id movido: {moved_number}")
        print(f"  wa_token: {_mask_token(utel_branch.wa_token)} (enmascarado, incluso en modo ejecución)")
        print()
        print("  Leads/Conversations existentes de la branch de origen NO se tocaron —")
        print("  quedan como están, esa branch simplemente ya no recibirá mensajes nuevos.")

    return 0


def _parse_origin_branch_id(argv: list[str]) -> uuid.UUID | None:
    for arg in argv:
        if arg.startswith("--origin-branch-id="):
            raw = arg.split("=", 1)[1]
            try:
                return uuid.UUID(raw)
            except ValueError:
                print(f"--origin-branch-id inválido (no es un UUID): {raw!r}")
                sys.exit(2)
    return None


async def main() -> int:
    argv = sys.argv[1:]
    execute = "--execute" in argv
    origin_branch_id = _parse_origin_branch_id(argv)
    if execute:
        return await _execute_mode(origin_branch_id)
    return await _audit_mode(origin_branch_id)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
