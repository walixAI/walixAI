"""Sprint 13A — Verifica CRUD de Deals y aislamiento RLS entre tenants.

Checks:
  1. Crear deal en tenant A (clínica beta)
  2. GET /api/deals lo incluye
  3. GET /api/deals/{id} devuelve el deal correcto
  4. PATCH mueve de etapa y marca is_won=True
  5. GET confirma cambios de PATCH
  6. RLS: deal de tenant A NO visible con credenciales de tenant B
  7. DELETE elimina el deal
  8. GET confirma eliminación (404)

Uso:
    cd backend
    .venv/bin/python scripts/test_deals.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE = "http://localhost:8000/api"

# Tenant A — clínica beta
TENANT_A_EMAIL = "asesor.con@clinica.com"
TENANT_A_PWD   = "walix2026"

# Tenant B — otro tenant para prueba de aislamiento
TENANT_B_EMAIL = "test4@mail.com"
TENANT_B_PWD   = "walix2026"

_PASS = "✅ PASS"
_FAIL = "❌ FAIL"
_results: list[bool] = []


def check(label: str, ok: bool) -> None:
    _results.append(ok)
    print(f"  {_PASS if ok else _FAIL}  {label}")


async def login(client: httpx.AsyncClient, email: str, pwd: str) -> str:
    r = await client.post(f"{BASE}/auth/login", json={"email": email, "password": pwd})
    if r.status_code != 200:
        print(f"  ❌ Login falló para {email}: {r.status_code} {r.text[:100]}")
        sys.exit(1)
    return r.json()["access_token"]


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        # ── Autenticación ──────────────────────────────────────────────────────
        token_a = await login(c, TENANT_A_EMAIL, TENANT_A_PWD)
        token_b = await login(c, TENANT_B_EMAIL, TENANT_B_PWD)
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}

        # Obtener datos del tenant A
        me = (await c.get(f"{BASE}/auth/me", headers=ha)).json()
        tenant_id_a = me["user"]["tenant_id"]

        # Obtener una etapa y lead del tenant A
        board = (await c.get(f"{BASE}/pipeline/board", headers=ha)).json()
        stages = sorted(board["stages"], key=lambda s: s["order_index"])
        open_stages = [s for s in stages if not s["is_won"] and not s["is_lost"]]
        stage_1_id = open_stages[0]["id"]
        stage_2_id = open_stages[1]["id"] if len(open_stages) > 1 else stage_1_id

        leads_r = (await c.get(f"{BASE}/v1/contacts?limit=1", headers=ha)).json()
        lead_id = leads_r["items"][0]["id"]

        print(f"\nTenant A: {tenant_id_a}")
        print(f"Lead:     {lead_id}")
        print(f"Etapa 1:  {stage_1_id}  →  Etapa 2: {stage_2_id}\n")

        created_id: str | None = None

        # ── Check 1: Crear deal ────────────────────────────────────────────────
        r = await c.post(f"{BASE}/deals", headers=ha, json={
            "lead_id":           lead_id,
            "pipeline_stage_id": stage_1_id,
            "title":             "Test Deal Sprint13A",
            "amount":            "9500.00",
            "probability":       45,
            "expected_close_date": "2026-08-01",
        })
        ok = r.status_code == 201
        check("POST /api/deals → 201", ok)
        if not ok:
            print(f"     Error: {r.status_code} {r.text[:200]}")
            return

        deal = r.json()
        created_id = deal["id"]
        check("Deal tiene tenant_id correcto", deal["tenant_id"] == tenant_id_a)
        check("Deal tiene title correcto", deal["title"] == "Test Deal Sprint13A")
        check("Deal amount = 9500.00", float(deal["amount"]) == 9500.0)
        check("Deal probability = 45", deal["probability"] == 45)

        # ── Check 2: GET list incluye el deal ─────────────────────────────────
        r = await c.get(f"{BASE}/deals", headers=ha)
        check("GET /api/deals → 200", r.status_code == 200)
        ids_in_list = [d["id"] for d in r.json()["items"]]
        check("Deal aparece en el listado", created_id in ids_in_list)

        # ── Check 3: GET individual ────────────────────────────────────────────
        r = await c.get(f"{BASE}/deals/{created_id}", headers=ha)
        check("GET /api/deals/{id} → 200", r.status_code == 200)
        check("GET devuelve el deal correcto", r.json()["id"] == created_id)

        # ── Check 4: PATCH — mover etapa + marcar won ─────────────────────────
        r = await c.patch(f"{BASE}/deals/{created_id}", headers=ha, json={
            "pipeline_stage_id": stage_2_id,
            "is_won": True,
            "amount": "12000.00",
        })
        check("PATCH /api/deals/{id} → 200", r.status_code == 200)

        # ── Check 5: Verificar cambios del PATCH ──────────────────────────────
        r = await c.get(f"{BASE}/deals/{created_id}", headers=ha)
        updated = r.json()
        check("PATCH actualizó pipeline_stage_id", updated["pipeline_stage_id"] == stage_2_id)
        check("PATCH marcó is_won=True", updated["is_won"] is True)
        check("PATCH actualizó amount a 12000", float(updated["amount"]) == 12000.0)

        # ── Check 6: Aislamiento — tenant B no ve deal de tenant A ───────────
        r = await c.get(f"{BASE}/deals/{created_id}", headers=hb)
        check("RLS: tenant B recibe 404 al pedir deal de tenant A", r.status_code == 404)

        r = await c.get(f"{BASE}/deals", headers=hb)
        ids_b = [d["id"] for d in r.json().get("items", [])]
        check("RLS: deal de tenant A no aparece en listado de tenant B", created_id not in ids_b)

        # ── Check 7: DELETE ────────────────────────────────────────────────────
        r = await c.delete(f"{BASE}/deals/{created_id}", headers=ha)
        check("DELETE /api/deals/{id} → 204", r.status_code == 204)

        # ── Check 8: GET post-delete → 404 ───────────────────────────────────
        r = await c.get(f"{BASE}/deals/{created_id}", headers=ha)
        check("GET después de DELETE → 404", r.status_code == 404)

    # ── Resumen ────────────────────────────────────────────────────────────────
    total  = len(_results)
    passed = sum(_results)
    print(f"\n{'─'*50}")
    print(f"  {passed}/{total} checks PASS")
    if passed < total:
        print("  ❌ Algunos checks fallaron — revisar logs arriba")
        sys.exit(1)
    else:
        print("  ✅ Sprint 13A — Deals CRUD + RLS: TODO PASS")


if __name__ == "__main__":
    asyncio.run(main())
