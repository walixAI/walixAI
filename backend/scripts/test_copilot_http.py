"""test_copilot_http.py — C4: verifica los endpoints HTTP del Copiloto.

Checks:
  a) POST /api/ai/copilot/chat — turno con tool de lectura (get_pipeline_status)
  b) GET  /api/ai/copilot/history — devuelve las filas guardadas del turno a)
  c) Aislamiento: usuario B del mismo tenant NO puede leer el historial de usuario A
  d) DELETE /api/ai/copilot/history — borra la sesión; GET devuelve []
  e) POST /api/ai/copilot/chat con entity_type/entity_id — responde OK

Uso:
    cd backend
    .venv/bin/python scripts/test_copilot_http.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE = "http://localhost:8000/api"

# Usuario A: propietario de la clínica
USER_A_EMAIL = "owner@clinica.com"
USER_A_PWD   = "walix2026"

# Usuario B: asesor del MISMO tenant (para test de aislamiento)
USER_B_EMAIL = "asesor.con@clinica.com"
USER_B_PWD   = "walix2026"

SESSION_ID = f"test-c4-{uuid.uuid4().hex[:8]}"

_PASS = "✅ PASS"
_FAIL = "❌ FAIL"
_results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    _results.append(ok)
    line = f"  {_PASS if ok else _FAIL}  {label}"
    if detail:
        line += f"\n         {detail}"
    print(line)


async def login(c: httpx.AsyncClient, email: str, pwd: str) -> str:
    r = await c.post(f"{BASE}/auth/login", json={"email": email, "password": pwd})
    if r.status_code != 200:
        print(f"  ❌ Login falló para {email}: {r.status_code} {r.text[:120]}")
        sys.exit(1)
    return r.json()["access_token"]


async def main() -> None:
    print(f"\n{'=' * 60}")
    print("  Walix C4 — Copiloto HTTP endpoints test")
    print(f"{'=' * 60}")
    print(f"  Session: {SESSION_ID}\n")

    async with httpx.AsyncClient(timeout=60) as c:
        # ── Auth ──────────────────────────────────────────────────────────────
        token_a = await login(c, USER_A_EMAIL, USER_A_PWD)
        token_b = await login(c, USER_B_EMAIL, USER_B_PWD)
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}

        me_a = (await c.get(f"{BASE}/auth/me", headers=ha)).json()
        me_b = (await c.get(f"{BASE}/auth/me", headers=hb)).json()
        tenant_a = me_a["user"]["tenant_id"]
        tenant_b = me_b["user"]["tenant_id"]
        same_tenant = tenant_a == tenant_b
        print(f"  Usuario A: {USER_A_EMAIL} (tenant {tenant_a[:8]}…)")
        print(f"  Usuario B: {USER_B_EMAIL} (tenant {tenant_b[:8]}…)")
        print(f"  Mismo tenant: {'SÍ ✓' if same_tenant else 'NO — ajustar credenciales'}\n")
        if not same_tenant:
            print("  ⚠️  Los dos usuarios deben ser del mismo tenant para el test de aislamiento")

        # ── (a) POST /ai/copilot/chat ─────────────────────────────────────────
        print("a) POST /api/ai/copilot/chat — mensaje que dispara tool de lectura")
        r = await c.post(
            f"{BASE}/ai/copilot/chat",
            headers=ha,
            json={
                "message": "¿Cuántos deals activos tengo en el pipeline?",
                "session_id": SESSION_ID,
            },
        )
        ok_a = r.status_code == 200
        body_a = r.json() if ok_a else {}
        check("status 200", ok_a, f"got {r.status_code}: {r.text[:120]}")
        check("reply no vacío", ok_a and len(body_a.get("reply", "")) > 10)
        check(
            "tool_calls_made incluye get_pipeline_status o get_my_deals",
            ok_a and any(
                t in body_a.get("tool_calls_made", [])
                for t in ("get_pipeline_status", "get_my_deals")
            ),
            f"tool_calls_made={body_a.get('tool_calls_made', [])}",
        )
        if ok_a:
            print(f"\n  reply: {body_a['reply'][:200]}…")
            print(f"  tool_calls_made: {body_a['tool_calls_made']}\n")

        # ── (b) GET /ai/copilot/history ───────────────────────────────────────
        print("b) GET /api/ai/copilot/history — devuelve filas del turno a)")
        r = await c.get(
            f"{BASE}/ai/copilot/history",
            headers=ha,
            params={"session_id": SESSION_ID},
        )
        ok_b = r.status_code == 200
        hist = r.json() if ok_b else []
        check("status 200", ok_b, f"got {r.status_code}: {r.text[:120]}")
        check("hay mensajes guardados (≥2)", ok_b and len(hist) >= 2, f"got {len(hist)} rows")
        roles_present = {m["role"] for m in hist}
        check("roles user+assistant presentes", {"user", "assistant"}.issubset(roles_present), f"roles={roles_present}")

        # ── (c) Aislamiento: usuario B NO ve el historial de A ─────────────────
        print("\nc) Aislamiento — usuario B no puede leer el historial de usuario A")
        r = await c.get(
            f"{BASE}/ai/copilot/history",
            headers=hb,
            params={"session_id": SESSION_ID},
        )
        ok_c = r.status_code == 200
        hist_b = r.json() if ok_c else []
        check(
            "usuario B obtiene [] para el mismo session_id",
            ok_c and len(hist_b) == 0,
            f"usuario B recibió {len(hist_b)} mensajes — FALLO DE AISLAMIENTO"
            if len(hist_b) > 0 else "",
        )

        # ── (d) DELETE /ai/copilot/history ────────────────────────────────────
        print("\nd) DELETE /api/ai/copilot/history — borra sesión de A")
        r = await c.delete(
            f"{BASE}/ai/copilot/history",
            headers=ha,
            params={"session_id": SESSION_ID},
        )
        check("status 204", r.status_code == 204, f"got {r.status_code}")

        r = await c.get(
            f"{BASE}/ai/copilot/history",
            headers=ha,
            params={"session_id": SESSION_ID},
        )
        hist_after = r.json() if r.status_code == 200 else ["error"]
        check("historial vacío tras DELETE", r.status_code == 200 and len(hist_after) == 0, f"got {len(hist_after)} rows")

        # ── (e) POST con entity_type/entity_id ───────────────────────────────
        print("\ne) POST /api/ai/copilot/chat con entity_type='deal' + entity_id falso")
        r = await c.post(
            f"{BASE}/ai/copilot/chat",
            headers=ha,
            json={
                "message": "Hola, ¿qué puedes hacer?",
                "session_id": SESSION_ID + "-e",
                "entity_type": "deal",
                "entity_id": str(uuid.uuid4()),  # UUID inexistente — debería manejar el fallo
            },
        )
        check("status 200 aun con entity_id inexistente", r.status_code == 200, f"got {r.status_code}: {r.text[:120]}")
        if r.status_code == 200:
            print(f"  reply: {r.json()['reply'][:200]}…")

    # ── Resumen ────────────────────────────────────────────────────────────────
    total = len(_results)
    passed = sum(_results)
    failed = total - passed
    print(f"\n{'─' * 60}")
    print(f"  {passed}/{total} checks pasaron  {'✅ PASS' if failed == 0 else f'❌ {failed} FAILs'}")
    print(f"{'─' * 60}\n")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
