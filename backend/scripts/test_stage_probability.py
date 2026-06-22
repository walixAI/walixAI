"""Sprint 14C.1 — Verifica probabilidad automática por etapa.

Checks:
  1.  GET /pipeline/stages → incluye campo default_probability (int)
  2.  Etapa won tiene default_probability = 100
  3.  Etapa lost tiene default_probability = 0
  4.  Etapas open tienen default_probability entre 1 y 99 (no cero-plano)
  5.  PATCH deal cambia etapa (sin probability) → deal.probability = default de nueva etapa
  6.  PATCH deal cambia etapa + probability explícito → probability NO se sobreescribe
  7.  Cleanup: deal de prueba eliminado

Uso:
    cd backend
    .venv/bin/python scripts/test_stage_probability.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE = "http://localhost:8000/api"

EMAIL = "asesor.con@clinica.com"
PWD   = "walix2026"

_PASS = "✅ PASS"
_FAIL = "❌ FAIL"
_results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    _results.append(ok)
    suffix = f"  ({detail})" if detail and not ok else ""
    print(f"  {_PASS if ok else _FAIL}  {label}{suffix}")


async def login(c: httpx.AsyncClient) -> str:
    r = await c.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PWD})
    if r.status_code != 200:
        print(f"❌ Login falló: {r.status_code} {r.text[:120]}")
        sys.exit(1)
    return r.json()["access_token"]


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        token = await login(c)
        h = {"Authorization": f"Bearer {token}"}

        # ── 1. GET /pipeline/stages → default_probability presente ────────────
        r = await c.get(f"{BASE}/pipeline/stages", headers=h)
        check("GET /pipeline/stages → 200", r.status_code == 200, r.text[:80])
        if r.status_code != 200:
            sys.exit(1)

        stages = r.json()
        check("stages no vacío", len(stages) > 0)

        s0 = stages[0]
        check("stage tiene campo default_probability",
              "default_probability" in s0,
              f"campos: {list(s0.keys())}")
        check("default_probability es int",
              isinstance(s0.get("default_probability"), int),
              str(s0.get("default_probability")))

        # ── 2. Won = 100, Lost = 0 ────────────────────────────────────────────
        won_stages  = [s for s in stages if s["is_won"]]
        lost_stages = [s for s in stages if s["is_lost"]]
        open_stages = [s for s in stages if not s["is_won"] and not s["is_lost"]]

        if won_stages:
            check("won stage → default_probability = 100",
                  all(s["default_probability"] == 100 for s in won_stages),
                  str([s["default_probability"] for s in won_stages]))
        else:
            print("  ⏭  Sin etapa won en este tenant — check omitido")

        if lost_stages:
            check("lost stage → default_probability = 0",
                  all(s["default_probability"] == 0 for s in lost_stages),
                  str([s["default_probability"] for s in lost_stages]))
        else:
            print("  ⏭  Sin etapa lost en este tenant — check omitido")

        # ── 4. Open stages graduadas ──────────────────────────────────────────
        if open_stages:
            probs = [s["default_probability"] for s in open_stages]
            check("open stages tienen default_probability entre 1 y 99",
                  all(1 <= p <= 99 for p in probs),
                  str(probs))
            check("open stages son distintas (si hay > 1)",
                  len(probs) == 1 or len(set(probs)) > 1,
                  str(probs))
        else:
            print("  ⏭  Sin etapas open — checks omitidos")

        if len(open_stages) < 2:
            print("  ⚠  Menos de 2 etapas open — checks de auto-probability limitados")

        # Necesitamos al menos 2 etapas open para los siguientes checks
        stage_a = open_stages[0]["id"]
        stage_b_prob = None
        if len(open_stages) > 1:
            stage_b = open_stages[1]
            stage_b_id   = stage_b["id"]
            stage_b_prob = stage_b["default_probability"]
        else:
            stage_b_id   = stage_a
            stage_b_prob = open_stages[0]["default_probability"]

        # Obtener un lead del tenant
        leads_r = (await c.get(f"{BASE}/v1/contacts?limit=1", headers=h)).json()
        if not leads_r.get("items"):
            print("❌ No hay leads en este tenant — abortar")
            sys.exit(1)
        lead_id = leads_r["items"][0]["id"]

        # ── Crear deal en stage_a con probability explícita = 25 ─────────────
        r = await c.post(f"{BASE}/deals", headers=h, json={
            "lead_id":           lead_id,
            "pipeline_stage_id": stage_a,
            "title":             "[TEST 14C1] Prueba probabilidad",
            "amount":            "1000.00",
            "probability":       25,
        })
        check("POST /deals → 201", r.status_code == 201, r.text[:100])
        if r.status_code != 201:
            sys.exit(1)
        deal_id = r.json()["id"]

        # ── 5. PATCH cambia etapa sin probability → auto-asignar ─────────────
        r = await c.patch(f"{BASE}/deals/{deal_id}", headers=h,
                          json={"pipeline_stage_id": stage_b_id})
        check("PATCH cambia etapa (sin probability) → 200", r.status_code == 200,
              r.text[:100])
        if r.status_code == 200:
            updated = r.json()
            check(
                f"deal.probability auto-asignado al default de nueva etapa ({stage_b_prob})",
                updated["probability"] == stage_b_prob,
                f"got {updated['probability']}, expected {stage_b_prob}",
            )

        # ── 6. PATCH cambia etapa + probability explícito → no sobreescribir ─
        # Volver a stage_a con probability explícito = 99
        r = await c.patch(f"{BASE}/deals/{deal_id}", headers=h, json={
            "pipeline_stage_id": stage_a,
            "probability":       99,
        })
        check("PATCH cambia etapa + probability explícito → 200",
              r.status_code == 200, r.text[:100])
        if r.status_code == 200:
            updated2 = r.json()
            check("probability explícito NO sobreescrito por default de etapa",
                  updated2["probability"] == 99,
                  f"got {updated2['probability']}, expected 99")

        # ── Cleanup ───────────────────────────────────────────────────────────
        print("\n── Cleanup ──────────────────────────────────────────────────")
        r = await c.delete(f"{BASE}/deals/{deal_id}", headers=h)
        check("DELETE deal de prueba → 204", r.status_code == 204)

    # ── Resumen ───────────────────────────────────────────────────────────────
    total  = len(_results)
    passed = sum(_results)
    print(f"\n{'─'*50}")
    print(f"  {passed}/{total} checks PASS")
    if passed < total:
        print("  ❌ Algunos checks fallaron — revisar arriba")
        sys.exit(1)
    else:
        print("  ✅ Sprint 14C.1 — Stage Probability: TODO PASS")


if __name__ == "__main__":
    asyncio.run(main())
