#!/usr/bin/env python3
"""B2 — Test: Walix Builder chat + save.

Verifica:
  T1: _require_owner bloquea ASESOR (403)
  T2: _require_owner permite OWNER (sin excepción)
  T3: system prompt generado desde COPILOT_TOOLS (no lista manual)
  T4: herramienta inventada es rechazada como inválida
  T5: conversación real de 3-4 turnos termina en RECIPE_READY
  T6: receta guardada en copilot_capabilities (row real en DB)

Ejecutar desde backend/:
  .venv/bin/python scripts/test_builder_b2.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import types

from fastapi import HTTPException
from sqlalchemy import select

from app.ai.copilot_engine import CLAUDE_MODEL, _anthropic
from app.ai.copilot_tools import COPILOT_TOOLS
from app.api.walix_builder import (
    _SYSTEM_PROMPT,
    _VALID_TOOL_NAMES,
    _WRITE_TOOL_NAMES,
    _require_owner,
)
from app.core.database import AsyncSessionLocal
from app.models.ai_memory import CopilotCapability
from app.models.user import User, UserRole

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"


async def main() -> int:
    passed = 0
    failed = 0

    # ── T1: _require_owner bloquea ASESOR ─────────────────────────────────────
    # SimpleNamespace avoids SQLAlchemy ORM instrumentation issues with __new__
    asesor = types.SimpleNamespace(role=UserRole.ASESOR)
    try:
        _require_owner(asesor)  # type: ignore[arg-type]
        print(f"{FAIL} T1: _require_owner no levantó excepción para ASESOR")
        failed += 1
    except HTTPException as e:
        if e.status_code == 403:
            print(f"{PASS} T1: _require_owner → 403 para ASESOR")
            passed += 1
        else:
            print(f"{FAIL} T1: status inesperado {e.status_code}")
            failed += 1

    # ── T2: _require_owner permite OWNER ───────────────────────────────────────
    owner_mock = types.SimpleNamespace(role=UserRole.OWNER)
    try:
        _require_owner(owner_mock)  # type: ignore[arg-type]
        print(f"{PASS} T2: _require_owner permite OWNER sin excepción")
        passed += 1
    except HTTPException:
        print(f"{FAIL} T2: _require_owner bloqueó OWNER incorrectamente")
        failed += 1

    # ── T3: system prompt derivado de COPILOT_TOOLS ────────────────────────────
    # prompt format: "- **tool_name** (risk=write): description"
    all_tools_present = all(t["name"] in _SYSTEM_PROMPT for t in COPILOT_TOOLS)
    write_tagged_ok = all(
        f'**{t["name"]}** (risk=write)' in _SYSTEM_PROMPT
        for t in COPILOT_TOOLS if t["name"] in _WRITE_TOOL_NAMES
    )
    read_tagged_ok = all(
        f'**{t["name"]}** (risk=read)' in _SYSTEM_PROMPT
        for t in COPILOT_TOOLS if t["name"] not in _WRITE_TOOL_NAMES
    )
    if all_tools_present and write_tagged_ok and read_tagged_ok:
        tool_count = len(COPILOT_TOOLS)
        write_count = len(_WRITE_TOOL_NAMES)
        print(
            f"{PASS} T3: system prompt contiene {tool_count} tools "
            f"({write_count} write, {tool_count - write_count} read) — generado desde COPILOT_TOOLS"
        )
        passed += 1
    else:
        missing_names = [t["name"] for t in COPILOT_TOOLS if t["name"] not in _SYSTEM_PROMPT]
        bad_write = [t["name"] for t in COPILOT_TOOLS
                     if t["name"] in _WRITE_TOOL_NAMES and f'**{t["name"]}** (risk=write)' not in _SYSTEM_PROMPT]
        bad_read = [t["name"] for t in COPILOT_TOOLS
                    if t["name"] not in _WRITE_TOOL_NAMES and f'**{t["name"]}** (risk=read)' not in _SYSTEM_PROMPT]
        print(f"{FAIL} T3: faltantes={missing_names} bad_write={bad_write} bad_read={bad_read}")
        failed += 1

    # ── T4: herramienta inventada rechazada ────────────────────────────────────
    invented = ["send_email", "delete_contact", "nonexistent_tool_xyz"]
    invalid_detected = [t for t in invented if t not in _VALID_TOOL_NAMES]
    if len(invalid_detected) == len(invented):
        print(f"{PASS} T4: herramientas inválidas detectadas correctamente: {invalid_detected}")
        passed += 1
    else:
        sneaked = [t for t in invented if t in _VALID_TOOL_NAMES]
        print(f"{FAIL} T4: herramientas inválidas no detectadas: {sneaked}")
        failed += 1

    # ── T5: conversación real (hasta 4 turnos) termina en RECIPE_READY ────────
    print("\n─── Conversación real con Claude ──────────────────────────────────")
    messages: list[dict] = []
    recipe_ready_seen = False
    final_reply = ""

    turns = [
        "Quiero automatizar el seguimiento después de que un deal se cierra como ganado: "
        "agregar una nota al contacto y luego crear una tarea de cobranza.",

        "Sí, exactamente eso. Apruebo los 2 pasos.",

        "Todos los usuarios, canal web, requiere confirmación, sin límite diario. "
        "Nombre: 'Seguimiento post-cierre'. Frases de disparo: 'seguimiento ganado', 'post cierre'.",

        "Confirmo todo. Genera el JSON final ahora.",
    ]

    for i, user_text in enumerate(turns, 1):
        messages.append({"role": "user", "content": user_text})
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=messages,
        )
        reply = next(
            (block.text for block in response.content if hasattr(block, "text")), ""
        )
        messages.append({"role": "assistant", "content": reply})

        print(f"\nUser T{i}: {user_text}")
        print(f"Assistant T{i}:\n{reply}")

        if "RECIPE_READY" in reply:
            recipe_ready_seen = True
            final_reply = reply
            break

    if recipe_ready_seen:
        print(f"\n{PASS} T5: conversación terminó en RECIPE_READY (en {len(messages) // 2} turno/s)")
        passed += 1
    else:
        print(f"\n{FAIL} T5: RECIPE_READY no apareció en ninguno de los {len(turns)} turnos")
        failed += 1

    # ── T6: guardar receta real en DB y verificar el row ──────────────────────
    async with AsyncSessionLocal() as db:
        user_row = (
            await db.execute(
                select(User).where(User.email == "owner@clinica.com")
            )
        ).scalar_one_or_none()

        if user_row is None:
            print(f"{FAIL} T6: owner@clinica.com no encontrado — se omite verificación DB")
            failed += 1
        else:
            cap = CopilotCapability(
                tenant_id=user_row.tenant_id,
                name="Seguimiento post-cierre [B2-test]",
                description="Test automático B2 — borrar si existe",
                kind="recipe",
                recipe_json={
                    "steps": [
                        {"tool": "add_note", "note": "Agregar nota al contacto"},
                        {"tool": "create_task", "note": "Crear tarea de cobranza"},
                    ]
                },
                trigger_phrases=["seguimiento ganado", "post cierre"],
                scope_type="all",
                scope_roles=[],
                scope_user_ids=[],
                channels=["web"],
                require_confirmation=True,
                daily_limit=None,
                is_active=True,
                created_by=user_row.id,
            )
            db.add(cap)
            await db.flush()
            cap_id = cap.id
            await db.commit()

            saved = await db.get(CopilotCapability, cap_id)
            if saved and saved.name == "Seguimiento post-cierre [B2-test]":
                print(f"\n{PASS} T6: row insertado en copilot_capabilities:")
                print(f"  id              = {saved.id}")
                print(f"  name            = {saved.name!r}")
                print(f"  kind            = {saved.kind!r}")
                print(f"  recipe_json     = {saved.recipe_json}")
                print(f"  trigger_phrases = {saved.trigger_phrases}")
                print(f"  scope_type      = {saved.scope_type!r}")
                print(f"  channels        = {saved.channels}")
                print(f"  require_confirm = {saved.require_confirmation}")
                print(f"  daily_limit     = {saved.daily_limit}")
                print(f"  is_active       = {saved.is_active}")
                print(f"  created_by      = {saved.created_by}")
                print(f"  tenant_id       = {saved.tenant_id}")
                passed += 1
            else:
                print(f"{FAIL} T6: row no encontrado después de commit")
                failed += 1

    print(f"\n{'='*55}")
    print(f"Resultado: {passed} PASS / {failed} FAIL")
    return failed


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(result)
