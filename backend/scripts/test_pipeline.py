"""Sprint 14A — Verifica endpoints Deal-based del Pipeline y deal_stage_history.

Checks:
  1.  GET /api/pipeline/stages → lista ordenada por order_index con campos correctos
  2.  GET /api/pipeline/deals → incluye stage_name para cada deal
  3.  GET /api/pipeline/deals → contact_last_activity_at correcto (null sin activity)
  4.  Crear lead_activity → contact_last_activity_at no-null en el endpoint
  5.  PATCH pipeline_stage_id → se crea fila en deal_stage_history (from/to correctos)
  6.  PATCH misma etapa → NO se crea fila adicional en deal_stage_history
  7.  DealCreate acepta source/notes nuevos
  8.  DealUpdate acepta lost_reason/lost_comment y los valida
  9.  lost_reason inválido → 422
  10. lost_comment > 500 chars → 422
  11. RLS: tenant B no ve deals de tenant A en /pipeline/deals
  12. Cleanup: datos de prueba eliminados

Uso:
    cd backend
    .venv/bin/python scripts/test_pipeline.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

import httpx
from sqlalchemy import text

from app.core.database import AsyncSessionLocal

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

        me = (await c.get(f"{BASE}/auth/me", headers=ha)).json()
        tenant_id_a = me["user"]["tenant_id"]

        # ── Resolver etapas del tenant A ──────────────────────────────────────
        r = await c.get(f"{BASE}/pipeline/stages", headers=ha)
        check("GET /pipeline/stages → 200", r.status_code == 200)
        stages = r.json()
        check("stages no vacío", len(stages) > 0)
        check("stages ordenados por order_index",
              all(stages[i]["order_index"] <= stages[i+1]["order_index"]
                  for i in range(len(stages)-1)))
        check("stage[0] tiene color, is_won, is_lost",
              all(f in stages[0] for f in ("color", "is_won", "is_lost", "name", "id")))

        open_stages = [s for s in stages if not s["is_won"] and not s["is_lost"]]
        stage_1 = open_stages[0]["id"]
        stage_2 = open_stages[1]["id"] if len(open_stages) > 1 else stage_1

        # Obtener lead existente del tenant A (de los seeds anteriores)
        leads_r = (await c.get(f"{BASE}/v1/contacts?limit=1", headers=ha)).json()
        lead_id = leads_r["items"][0]["id"]

        # ── Crear deal de prueba ──────────────────────────────────────────────
        r = await c.post(f"{BASE}/deals", headers=ha, json={
            "lead_id":           lead_id,
            "pipeline_stage_id": stage_1,
            "title":             "Test Pipeline 14A",
            "amount":            "7500.00",
            "source":            "referido",
            "notes":             "Nota de prueba Sprint 14A",
        })
        check("POST /deals con source/notes → 201", r.status_code == 201,
              r.text[:100] if r.status_code != 201 else "")
        if r.status_code != 201:
            return
        deal = r.json()
        deal_id = deal["id"]
        check("deal.source guardado", deal.get("source") == "referido")
        check("deal.notes guardado", deal.get("notes") == "Nota de prueba Sprint 14A")

        # ── GET /pipeline/deals — sin lead_activity → last_at null ───────────
        r = await c.get(f"{BASE}/pipeline/deals", headers=ha)
        check("GET /pipeline/deals → 200", r.status_code == 200)
        deal_items = r.json()
        our_deal = next((d for d in deal_items if d["id"] == deal_id), None)
        check("deal aparece en /pipeline/deals", our_deal is not None)
        if our_deal:
            check("stage_name presente", bool(our_deal.get("stage_name")))
            check("contact_last_activity_at es null sin actividad",
                  our_deal.get("contact_last_activity_at") is None)

        # ── Crear lead_activity en DB y verificar last_at ─────────────────────
        activity_id = uuid.uuid4()
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO lead_activities (id, tenant_id, lead_id, activity_type, created_at, updated_at)
                VALUES (:id, :tid, :lid, 'note', NOW(), NOW())
            """), {"id": activity_id, "tid": uuid.UUID(tenant_id_a), "lid": uuid.UUID(lead_id)})
            await db.commit()

        r = await c.get(f"{BASE}/pipeline/deals", headers=ha)
        our_deal2 = next((d for d in r.json() if d["id"] == deal_id), None)
        check("contact_last_activity_at no-null después de crear actividad",
              our_deal2 is not None and our_deal2.get("contact_last_activity_at") is not None)

        # ── PATCH cambia etapa → deal_stage_history creado ───────────────────
        r = await c.patch(f"{BASE}/deals/{deal_id}", headers=ha,
                          json={"pipeline_stage_id": stage_2})
        check("PATCH pipeline_stage_id → 200", r.status_code == 200)

        async with AsyncSessionLocal() as db:
            row = (await db.execute(text("""
                SELECT from_stage_id, to_stage_id FROM deal_stage_history
                WHERE deal_id = :did ORDER BY changed_at DESC LIMIT 1
            """), {"did": uuid.UUID(deal_id)})).fetchone()
        check("deal_stage_history creado tras PATCH de etapa", row is not None)
        if row:
            check("from_stage_id correcto", str(row[0]) == stage_1)
            check("to_stage_id correcto",   str(row[1]) == stage_2)

        # ── PATCH misma etapa → NO crea nueva fila ───────────────────────────
        async with AsyncSessionLocal() as db:
            count_before = (await db.execute(text(
                "SELECT COUNT(*) FROM deal_stage_history WHERE deal_id = :did",
            ), {"did": uuid.UUID(deal_id)})).scalar_one()

        await c.patch(f"{BASE}/deals/{deal_id}", headers=ha,
                      json={"pipeline_stage_id": stage_2})

        async with AsyncSessionLocal() as db:
            count_after = (await db.execute(text(
                "SELECT COUNT(*) FROM deal_stage_history WHERE deal_id = :did",
            ), {"did": uuid.UUID(deal_id)})).scalar_one()
        check("PATCH misma etapa NO crea fila adicional", count_before == count_after)

        # ── PATCH lost_reason + lost_comment ─────────────────────────────────
        r = await c.patch(f"{BASE}/deals/{deal_id}", headers=ha, json={
            "is_lost": True,
            "lost_reason": "price",
            "lost_comment": "El precio era demasiado alto.",
        })
        check("PATCH lost_reason válido → 200", r.status_code == 200)
        updated = r.json()
        check("lost_reason guardado", updated.get("lost_reason") == "price")
        check("lost_comment guardado", updated.get("lost_comment") == "El precio era demasiado alto.")

        # ── lost_reason inválido → 422 ────────────────────────────────────────
        r = await c.patch(f"{BASE}/deals/{deal_id}", headers=ha,
                          json={"lost_reason": "invalid_value"})
        check("lost_reason inválido → 422", r.status_code == 422)

        # ── lost_comment > 500 chars → 422 ───────────────────────────────────
        r = await c.patch(f"{BASE}/deals/{deal_id}", headers=ha,
                          json={"lost_comment": "x" * 501})
        check("lost_comment > 500 chars → 422", r.status_code == 422)

        # ── RLS: tenant B no ve deals de tenant A ────────────────────────────
        r = await c.get(f"{BASE}/pipeline/deals", headers=hb)
        check("RLS: /pipeline/deals 200 para tenant B", r.status_code == 200)
        ids_b = {d["id"] for d in r.json()}
        check("RLS: deal de tenant A no visible para tenant B", deal_id not in ids_b)

        # ── Cleanup ───────────────────────────────────────────────────────────
        print("\n── Cleanup ──────────────────────────────────────────────────")
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM lead_activities WHERE id = :id"
            ), {"id": activity_id})
            await db.commit()

        r = await c.delete(f"{BASE}/deals/{deal_id}", headers=ha)
        check("DELETE deal → 204", r.status_code == 204)

        # deal_stage_history cascade-deletes con el deal
        async with AsyncSessionLocal() as db:
            remaining = (await db.execute(text(
                "SELECT COUNT(*) FROM deal_stage_history WHERE deal_id = :did"
            ), {"did": uuid.UUID(deal_id)})).scalar_one()
        check("deal_stage_history eliminado en cascade", remaining == 0)

    # ── Resumen ───────────────────────────────────────────────────────────────
    total  = len(_results)
    passed = sum(_results)
    print(f"\n{'─'*50}")
    print(f"  {passed}/{total} checks PASS")
    if passed < total:
        print("  ❌ Algunos checks fallaron — revisar arriba")
        sys.exit(1)
    else:
        print("  ✅ Sprint 14A — Pipeline endpoints: TODO PASS")


if __name__ == "__main__":
    asyncio.run(main())
