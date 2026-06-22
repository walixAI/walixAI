"""Sprint 14C.2 — Verifica owner_id en Deals.

Checks:
  1.  POST /deals sin owner_id → owner_id == usuario autenticado
  2.  POST /deals con owner_id de otro usuario del mismo tenant → se respeta
  3.  POST /deals con owner_id de OTRO tenant → 422
  4.  DealRead incluye owner_id
  5.  GET /pipeline/deals incluye owner_id en cada item
  6.  GET /pipeline/users → devuelve usuarios del tenant con id/name/email
  7.  GET /pipeline/users → RLS: tenant B ve SUS usuarios, no los de tenant A
  8.  PATCH reasignando owner_id → persiste
  9.  PATCH owner_id = null → desasigna (null en respuesta)
  10. PATCH owner_id de otro tenant → 422
  11. DELETE cleanup → 204

Uso:
    cd backend
    .venv/bin/python scripts/test_deal_owner.py
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
        print(f"❌ Login falló para {email}: {r.status_code} {r.text[:80]}")
        sys.exit(1)
    return r.json()["access_token"]


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        token_a = await login(c, TENANT_A_EMAIL, TENANT_A_PWD)
        token_b = await login(c, TENANT_B_EMAIL, TENANT_B_PWD)
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}

        # ID del usuario autenticado como A
        me_a = (await c.get(f"{BASE}/auth/me", headers=ha)).json()
        user_a_id = me_a["user"]["id"]

        # Obtener un segundo usuario del tenant A (para check b y d)
        users_r = await c.get(f"{BASE}/pipeline/users", headers=ha)
        check("GET /pipeline/users → 200", users_r.status_code == 200,
              users_r.text[:80])
        if users_r.status_code != 200:
            sys.exit(1)

        all_users_a = users_r.json()
        check("pipeline/users devuelve lista con id/name/email",
              len(all_users_a) > 0 and all(
                  "id" in u and "name" in u and "email" in u
                  for u in all_users_a
              ), str(all_users_a[:1]))

        # Buscar un usuario distinto al asesor (para reasignación)
        other_user_a = next(
            (u for u in all_users_a if u["id"] != user_a_id),
            None,
        )

        # Un usuario del tenant B para intentar asignación cross-tenant
        me_b = (await c.get(f"{BASE}/auth/me", headers=hb)).json()
        user_b_id = me_b["user"]["id"]

        # Obtener lead de tenant A
        leads_r = (await c.get(f"{BASE}/v1/contacts?limit=1", headers=ha)).json()
        if not leads_r.get("items"):
            print("❌ No hay leads en tenant A — abortar")
            sys.exit(1)
        lead_id = leads_r["items"][0]["id"]

        # Etapas de tenant A
        stages_r = (await c.get(f"{BASE}/pipeline/stages", headers=ha)).json()
        open_stages = [s for s in stages_r if not s["is_won"] and not s["is_lost"]]
        stage_id = open_stages[0]["id"]

        deal_ids_to_cleanup: list[str] = []

        # ── Check 1: POST sin owner_id → auto-asigna al usuario autenticado ──
        r = await c.post(f"{BASE}/deals", headers=ha, json={
            "lead_id":           lead_id,
            "pipeline_stage_id": stage_id,
            "title":             "[TEST 14C2] Auto-owner",
            "amount":            "100.00",
        })
        check("POST /deals sin owner_id → 201", r.status_code == 201,
              r.text[:100])
        if r.status_code != 201:
            sys.exit(1)
        deal_auto = r.json()
        deal_ids_to_cleanup.append(deal_auto["id"])

        check("DealRead incluye owner_id", "owner_id" in deal_auto,
              str(list(deal_auto.keys())))
        check("owner_id auto-asignado == usuario autenticado",
              deal_auto.get("owner_id") == user_a_id,
              f"got={deal_auto.get('owner_id')} expected={user_a_id}")

        # ── Check 2: POST con owner_id explícito (otro usuario mismo tenant) ─
        if other_user_a:
            r2 = await c.post(f"{BASE}/deals", headers=ha, json={
                "lead_id":           lead_id,
                "pipeline_stage_id": stage_id,
                "title":             "[TEST 14C2] Explicit-owner",
                "amount":            "200.00",
                "owner_id":          other_user_a["id"],
            })
            check("POST /deals con owner_id de otro usuario mismo tenant → 201",
                  r2.status_code == 201, r2.text[:100])
            if r2.status_code == 201:
                deal_explicit = r2.json()
                deal_ids_to_cleanup.append(deal_explicit["id"])
                check("owner_id respetado (no sobreescrito)",
                      deal_explicit.get("owner_id") == other_user_a["id"],
                      f"got={deal_explicit.get('owner_id')}")
        else:
            print("  ⏭  Solo un usuario en tenant A — checks de owner explícito omitidos")

        # ── Check 3: POST con owner_id de OTRO tenant → 422 ──────────────────
        r3 = await c.post(f"{BASE}/deals", headers=ha, json={
            "lead_id":           lead_id,
            "pipeline_stage_id": stage_id,
            "title":             "[TEST 14C2] Cross-tenant owner",
            "amount":            "0.00",
            "owner_id":          user_b_id,
        })
        check("POST con owner_id de otro tenant → 422",
              r3.status_code == 422,
              f"got {r3.status_code}")

        # ── Check 5: GET /pipeline/deals incluye owner_id ─────────────────────
        r5 = await c.get(f"{BASE}/pipeline/deals", headers=ha)
        check("GET /pipeline/deals → 200", r5.status_code == 200)
        if r5.status_code == 200:
            items = r5.json()
            our_deal = next((d for d in items if d["id"] == deal_auto["id"]), None)
            check("deal aparece en /pipeline/deals", our_deal is not None)
            if our_deal:
                check("pipeline/deals incluye owner_id",
                      "owner_id" in our_deal,
                      str(list(our_deal.keys())))
                check("pipeline/deals owner_id == usuario autenticado",
                      our_deal.get("owner_id") == user_a_id,
                      f"got={our_deal.get('owner_id')}")

        # ── Check 7: RLS pipeline/users — tenant B ve sus propios usuarios ────
        r7 = await c.get(f"{BASE}/pipeline/users", headers=hb)
        check("GET /pipeline/users tenant B → 200", r7.status_code == 200)
        if r7.status_code == 200:
            users_b = r7.json()
            ids_b = {u["id"] for u in users_b}
            ids_a = {u["id"] for u in all_users_a}
            check("tenant B no ve usuarios de tenant A",
                  len(ids_a & ids_b) == 0,
                  f"overlap={ids_a & ids_b}")

        # ── Check 8: PATCH reasignando owner_id ──────────────────────────────
        if other_user_a:
            r8 = await c.patch(f"{BASE}/deals/{deal_auto['id']}", headers=ha,
                               json={"owner_id": other_user_a["id"]})
            check("PATCH reasignar owner_id → 200", r8.status_code == 200,
                  r8.text[:100])
            if r8.status_code == 200:
                check("owner_id reasignado persiste",
                      r8.json().get("owner_id") == other_user_a["id"],
                      str(r8.json().get("owner_id")))

        # ── Check 9: PATCH owner_id = null → desasigna ───────────────────────
        r9 = await c.patch(f"{BASE}/deals/{deal_auto['id']}", headers=ha,
                           json={"owner_id": None})
        check("PATCH owner_id=null → 200", r9.status_code == 200, r9.text[:100])
        if r9.status_code == 200:
            check("owner_id desasignado (null en respuesta)",
                  r9.json().get("owner_id") is None,
                  str(r9.json().get("owner_id")))

        # ── Check 10: PATCH owner_id de otro tenant → 422 ────────────────────
        r10 = await c.patch(f"{BASE}/deals/{deal_auto['id']}", headers=ha,
                            json={"owner_id": user_b_id})
        check("PATCH owner_id de otro tenant → 422",
              r10.status_code == 422,
              f"got {r10.status_code}")

        # ── Cleanup ───────────────────────────────────────────────────────────
        print("\n── Cleanup ──────────────────────────────────────────────────")
        for did in deal_ids_to_cleanup:
            r_del = await c.delete(f"{BASE}/deals/{did}", headers=ha)
            check(f"DELETE deal {did[:8]}… → 204", r_del.status_code == 204)

    # ── Resumen ───────────────────────────────────────────────────────────────
    total  = len(_results)
    passed = sum(_results)
    print(f"\n{'─'*50}")
    print(f"  {passed}/{total} checks PASS")
    if passed < total:
        print("  ❌ Algunos checks fallaron — revisar arriba")
        sys.exit(1)
    else:
        print("  ✅ Sprint 14C.2 — Deal Owner: TODO PASS")


if __name__ == "__main__":
    asyncio.run(main())
