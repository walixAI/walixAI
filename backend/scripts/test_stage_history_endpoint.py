"""Sprint 14C.3-back — Verifica GET /api/deals/{id}/stage-history.

Checks:
  1.  Crear deal → GET /stage-history devuelve lista vacía (sin movimientos aún)
  2.  PATCH etapa (movimiento 1) → historial tiene 1 fila
  3.  PATCH etapa (movimiento 2) → historial tiene 2 filas
  4.  Orden: cambios devueltos DESC por changed_at
  5.  to_stage_name resuelto (string, no null)
  6.  from_stage_name resuelto en movimiento 2 (no null, no confundir con movimiento 1)
  7.  Primera entrada del historial (movimiento 1): from_stage_id == null ó from_stage_name == null
      (el primer PATCH no tiene "etapa anterior" registrada con from_stage_id)
      — nota: el PATCH sí guarda from_stage_id = etapa original, pero si se creó sin historial
        previo, el primer registro muestra from = etapa de creación (not null). El check real es:
        el campo from_stage_name puede ser null solo si from_stage_id es null.
  8.  Aislamiento: tenant B recibe 404 para el deal de tenant A
  9.  Deal inexistente → 404
  10. Cleanup: deal eliminado, historial en cascade

Uso:
    cd backend
    .venv/bin/python scripts/test_stage_history_endpoint.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

import httpx

BASE = "http://localhost:8000/api"

TENANT_A_EMAIL = "asesor.con@clinica.com"
TENANT_A_PWD   = "walix2026"
TENANT_B_EMAIL = "test4@mail.com"
TENANT_B_PWD   = "walix2026"

_PASS = "✅ PASS"
_FAIL = "❌ FAIL"
_results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    _results.append(ok)
    suffix = f"  ({detail})" if detail and not ok else ""
    print(f"  {_PASS if ok else _FAIL}  {label}{suffix}")


async def login(c: httpx.AsyncClient, email: str, pwd: str) -> str:
    r = await c.post(f"{BASE}/auth/login", json={"email": email, "password": pwd})
    if r.status_code != 200:
        print(f"❌ Login falló para {email}: {r.status_code}")
        sys.exit(1)
    return r.json()["access_token"]


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        token_a = await login(c, TENANT_A_EMAIL, TENANT_A_PWD)
        token_b = await login(c, TENANT_B_EMAIL, TENANT_B_PWD)
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}

        # ── Resolver etapas del tenant A ──────────────────────────────────────
        stages_r = (await c.get(f"{BASE}/pipeline/stages", headers=ha)).json()
        open_stages = [s for s in stages_r if not s["is_won"] and not s["is_lost"]]
        if len(open_stages) < 2:
            print("❌ Se necesitan ≥ 2 etapas open en el tenant A")
            sys.exit(1)
        stage_1 = open_stages[0]
        stage_2 = open_stages[1]
        stage_3 = open_stages[2] if len(open_stages) > 2 else None

        # ── Obtener lead del tenant A ─────────────────────────────────────────
        leads_r = (await c.get(f"{BASE}/v1/contacts?limit=1", headers=ha)).json()
        if not leads_r.get("items"):
            print("❌ No hay leads en tenant A")
            sys.exit(1)
        lead_id = leads_r["items"][0]["id"]

        # ── Crear deal en stage_1 ─────────────────────────────────────────────
        r = await c.post(f"{BASE}/deals", headers=ha, json={
            "lead_id":           lead_id,
            "pipeline_stage_id": stage_1["id"],
            "title":             "[TEST 14C3] Stage history endpoint",
            "amount":            "5000.00",
        })
        check("POST /deals → 201", r.status_code == 201, r.text[:100])
        if r.status_code != 201:
            sys.exit(1)
        deal_id = r.json()["id"]

        # ── Check 1: historial vacío recién creado ────────────────────────────
        r1 = await c.get(f"{BASE}/deals/{deal_id}/stage-history", headers=ha)
        check("GET /stage-history → 200", r1.status_code == 200, r1.text[:80])
        check("historial vacío al crear deal (sin PATCH aún)", r1.json() == [],
              str(r1.json()[:1]))

        # ── Movimiento 1: stage_1 → stage_2 ──────────────────────────────────
        r_p1 = await c.patch(f"{BASE}/deals/{deal_id}", headers=ha,
                             json={"pipeline_stage_id": stage_2["id"]})
        check("PATCH movimiento 1 (→ stage_2) → 200", r_p1.status_code == 200)

        r2 = await c.get(f"{BASE}/deals/{deal_id}/stage-history", headers=ha)
        check("historial tiene 1 fila tras movimiento 1", len(r2.json()) == 1,
              f"got {len(r2.json())}")

        h1 = r2.json()[0] if r2.json() else {}
        check("to_stage_id correcto en movimiento 1",
              h1.get("to_stage_id") == stage_2["id"],
              f"got {h1.get('to_stage_id')}")
        check("to_stage_name resuelto (no null)",
              isinstance(h1.get("to_stage_name"), str) and len(h1.get("to_stage_name", "")) > 0,
              str(h1.get("to_stage_name")))
        check("from_stage_id == stage_1 en movimiento 1",
              h1.get("from_stage_id") == stage_1["id"],
              f"got {h1.get('from_stage_id')}")
        check("from_stage_name resuelto (no null, desde stage_1)",
              isinstance(h1.get("from_stage_name"), str),
              str(h1.get("from_stage_name")))

        # ── Movimiento 2: stage_2 → stage_3 (o stage_1 si no hay stage_3) ────
        target_stage = stage_3 if stage_3 else stage_1
        r_p2 = await c.patch(f"{BASE}/deals/{deal_id}", headers=ha,
                             json={"pipeline_stage_id": target_stage["id"]})
        check("PATCH movimiento 2 → 200", r_p2.status_code == 200)

        r3 = await c.get(f"{BASE}/deals/{deal_id}/stage-history", headers=ha)
        history = r3.json()
        check("historial tiene 2 filas tras movimiento 2", len(history) == 2,
              f"got {len(history)}")

        # ── Check 4: orden DESC por changed_at ───────────────────────────────
        if len(history) == 2:
            check("orden DESC: primer item es el movimiento más reciente",
                  history[0]["to_stage_id"] == target_stage["id"],
                  f"got to_stage_id={history[0].get('to_stage_id')}")
            check("segundo item es el movimiento anterior (stage_2)",
                  history[1]["to_stage_id"] == stage_2["id"],
                  f"got to_stage_id={history[1].get('to_stage_id')}")

        # ── Check 5-6: nombres resueltos en ambas filas ───────────────────────
        for i, item in enumerate(history):
            check(f"fila {i}: to_stage_name es string",
                  isinstance(item.get("to_stage_name"), str),
                  str(item.get("to_stage_name")))
            if item.get("from_stage_id") is not None:
                check(f"fila {i}: from_stage_name resuelto (not null cuando from_stage_id not null)",
                      isinstance(item.get("from_stage_name"), str),
                      str(item.get("from_stage_name")))
            else:
                check(f"fila {i}: from_stage_name es null cuando from_stage_id es null",
                      item.get("from_stage_name") is None,
                      str(item.get("from_stage_name")))

        # ── Check 8: aislamiento — tenant B recibe 404 ───────────────────────
        r8 = await c.get(f"{BASE}/deals/{deal_id}/stage-history", headers=hb)
        check("tenant B → 404 para deal de tenant A",
              r8.status_code == 404,
              f"got {r8.status_code}")

        # ── Check 9: deal inexistente → 404 ──────────────────────────────────
        import uuid as _uuid
        fake_id = str(_uuid.uuid4())
        r9 = await c.get(f"{BASE}/deals/{fake_id}/stage-history", headers=ha)
        check("deal inexistente → 404", r9.status_code == 404,
              f"got {r9.status_code}")

        # ── Cleanup ───────────────────────────────────────────────────────────
        print("\n── Cleanup ──────────────────────────────────────────────────")
        r_del = await c.delete(f"{BASE}/deals/{deal_id}", headers=ha)
        check("DELETE deal → 204", r_del.status_code == 204)

        # Verificar cascade en historial
        from sqlalchemy import text
        from app.core.database import AsyncSessionLocal
        import uuid as _uuid2
        async with AsyncSessionLocal() as db:
            remaining = (await db.execute(text(
                "SELECT COUNT(*) FROM deal_stage_history WHERE deal_id = :did"
            ), {"did": _uuid2.UUID(deal_id)})).scalar_one()
        check("deal_stage_history eliminado en cascade", remaining == 0,
              f"quedan {remaining} filas")

    # ── Resumen ───────────────────────────────────────────────────────────────
    total  = len(_results)
    passed = sum(_results)
    print(f"\n{'─'*50}")
    print(f"  {passed}/{total} checks PASS")
    if passed < total:
        print("  ❌ Algunos checks fallaron — revisar arriba")
        sys.exit(1)
    else:
        print("  ✅ Sprint 14C.3-back — Stage History Endpoint: TODO PASS")


if __name__ == "__main__":
    asyncio.run(main())
