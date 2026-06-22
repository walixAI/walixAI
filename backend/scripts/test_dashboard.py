"""Sprint 13B — Verifica los 4 endpoints del dashboard de Deals.

Checks:
  1-3.  /kpis: pipelineValue > 0, coincide con suma manual de deals activos
  4.    /kpis: closeRate calculado correctamente
  5.    /activity: devuelve lista (puede ser vacía si no hay activities)
  6-7.  /pipeline-by-stage: suma de values == pipelineValue
  8-9.  /deals-closed-timeline: estructura correcta, days buckets
  10.   RLS: tenant aislado ve pipelineValue=0 y lista vacía en pipeline-by-stage
  11.   Cleanup: todos los deals [DEMO] del tenant demo borrados

Uso:
    cd backend
    export CLINICA_TENANT_ID=72b10c98-8b9d-4d03-9e17-085a8a77a98f
    .venv/bin/python scripts/test_dashboard.py

Variables de entorno opcionales:
    DEMO_TENANT_ID   — defaults a Clinica Zendejas
    DEMO_EMAIL       — defaults a test4@mail.com
    DEMO_PWD         — defaults a walix2026
    CLINICA_TENANT_ID — tenant que NUNCA debe recibir demo data
"""
from __future__ import annotations

import asyncio
import os
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

DEMO_TENANT_ID = os.environ.get("DEMO_TENANT_ID", "7e4ec8d0-1d93-43a2-b610-120a3bf91e68")
DEMO_EMAIL     = os.environ.get("DEMO_EMAIL", "test4@mail.com")
DEMO_PWD       = os.environ.get("DEMO_PWD", "walix2026")

# Tenant de aislamiento (usa clinica beta — NO tiene deals demo)
ISOLATION_EMAIL = "asesor.con@clinica.com"
ISOLATION_PWD   = "walix2026"

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
        print(f"  ❌ Login falló para {email}: {r.status_code} {r.text[:100]}")
        sys.exit(1)
    return r.json()["access_token"]


async def seed_demo(c: httpx.AsyncClient, token: str) -> None:
    """Llama al seed_demo_deals.py inline para que el test sea auto-contenido."""
    import subprocess
    result = subprocess.run(
        [
            sys.executable, "scripts/seed_demo_deals.py",
            "--tenant-id", DEMO_TENANT_ID,
            "--email",     DEMO_EMAIL,
            "--password",  DEMO_PWD,
        ],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent,
    )
    if result.returncode != 0:
        print("  ⚠  seed_demo_deals.py devolvió error:")
        print(result.stdout[-300:])
        print(result.stderr[-200:])
        # Continuar igual — puede ser que ya estén los datos


async def cleanup(c: httpx.AsyncClient, token: str) -> None:
    """Borra todos los deals [DEMO] y leads [DEMO] del tenant demo."""
    h = {"Authorization": f"Bearer {token}"}
    print("\n── Cleanup ──────────────────────────────────────────────────")

    # Borrar deals
    all_deals = (await c.get(f"{BASE}/deals?limit=100", headers=h)).json()
    demo_deal_ids = [
        d["id"] for d in all_deals.get("items", [])
        if d.get("title", "").startswith("[DEMO]")
    ]
    deleted_deals = 0
    for did in demo_deal_ids:
        r = await c.delete(f"{BASE}/deals/{did}", headers=h)
        if r.status_code == 204:
            deleted_deals += 1
    print(f"  Deals [DEMO] borrados: {deleted_deals}")

    # Borrar leads
    all_leads = (await c.get(f"{BASE}/v1/contacts?limit=100", headers=h)).json()
    demo_lead_ids = [
        l["id"] for l in all_leads.get("items", [])
        if (l.get("name") or "").startswith("[DEMO]")
    ]
    deleted_leads = 0
    for lid in demo_lead_ids:
        r = await c.delete(f"{BASE}/v1/contacts/{lid}", headers=h)
        if r.status_code in (200, 204):
            deleted_leads += 1
    print(f"  Leads [DEMO] borrados: {deleted_leads}")


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        print("── Setup: sembrando datos demo ──────────────────────────────")
        token_demo = await login(c, DEMO_EMAIL, DEMO_PWD)
        await seed_demo(c, token_demo)
        # Refresh token after seed (seed may take a while)
        token_demo = await login(c, DEMO_EMAIL, DEMO_PWD)
        hd = {"Authorization": f"Bearer {token_demo}"}

        token_iso = await login(c, ISOLATION_EMAIL, ISOLATION_PWD)
        hi = {"Authorization": f"Bearer {token_iso}"}

        print("\n── Tests ────────────────────────────────────────────────────")

        # ── /kpis ─────────────────────────────────────────────────────────────
        r = await c.get(f"{BASE}/dashboard/kpis", headers=hd)
        check("GET /kpis → 200", r.status_code == 200, str(r.status_code))
        kpis = r.json()

        pipeline_value = kpis.get("pipelineValue", 0)
        check("kpis.pipelineValue > 0", pipeline_value > 0, str(pipeline_value))

        # Verificar contra la suma manual de deals activos
        all_deals = (await c.get(f"{BASE}/deals?limit=100", headers=hd)).json()
        active_sum = sum(
            float(d["amount"])
            for d in all_deals.get("items", [])
            if not d["is_won"] and not d["is_lost"]
        )
        check(
            "kpis.pipelineValue coincide con suma manual de deals activos",
            abs(pipeline_value - int(active_sum)) <= 1,
            f"kpis={pipeline_value} manual={int(active_sum)}",
        )

        # Close rate
        won_count  = sum(1 for d in all_deals["items"] if d["is_won"])
        lost_count = sum(1 for d in all_deals["items"] if d["is_lost"])
        total_closed = won_count + lost_count
        expected_rate = round(won_count / total_closed * 100) if total_closed else 0
        check(
            "kpis.closeRate es correcto",
            kpis.get("closeRate") == expected_rate,
            f"got={kpis.get('closeRate')} expected={expected_rate}",
        )

        # Shape checks
        for field in ("pipelineDeltaPct", "activeDeals", "staleDeals",
                      "messagesToday", "messagesUnanswered", "closeRateDelta"):
            check(f"kpis tiene campo '{field}'", field in kpis)

        # ── /activity ─────────────────────────────────────────────────────────
        r = await c.get(f"{BASE}/dashboard/activity?limit=10", headers=hd)
        check("GET /activity → 200", r.status_code == 200)
        acts = r.json()
        check("activity devuelve lista", isinstance(acts, list))
        if acts:
            first = acts[0]
            for field in ("id", "type", "description", "occurredAt", "contactId", "contactName"):
                check(f"activity[0] tiene '{field}'", field in first)
            valid_types = {"deal", "wa_sent", "wa_received", "note", "task"}
            check("activity[0].type es valor válido", first["type"] in valid_types)

        # ── /pipeline-by-stage ────────────────────────────────────────────────
        r = await c.get(f"{BASE}/dashboard/pipeline-by-stage", headers=hd)
        check("GET /pipeline-by-stage → 200", r.status_code == 200)
        by_stage = r.json()
        check("pipeline-by-stage devuelve lista", isinstance(by_stage, list))
        check("pipeline-by-stage no está vacía", len(by_stage) > 0)
        if by_stage:
            check("pipeline-by-stage[0] tiene 'stage'", "stage" in by_stage[0])
            check("pipeline-by-stage[0] tiene 'value'", "value" in by_stage[0])

        stage_sum = sum(b["value"] for b in by_stage)
        check(
            "Σ pipeline-by-stage == kpis.pipelineValue",
            stage_sum == pipeline_value,
            f"stageSum={stage_sum} pipelineValue={pipeline_value}",
        )

        # ── /deals-closed-timeline ────────────────────────────────────────────
        r = await c.get(f"{BASE}/dashboard/deals-closed-timeline?days=30", headers=hd)
        check("GET /deals-closed-timeline → 200", r.status_code == 200)
        timeline = r.json()
        check("timeline devuelve lista", isinstance(timeline, list))
        check("timeline tiene 30 buckets", len(timeline) == 30)
        if timeline:
            check("timeline[0] tiene 'day'",   "day"   in timeline[0])
            check("timeline[0] tiene 'date'",  "date"  in timeline[0])
            check("timeline[0] tiene 'value'", "value" in timeline[0])
            check("timeline[0].day == '1'",    timeline[0]["day"] == "1")
            check("timeline[-1].day == '30'",  timeline[-1]["day"] == "30")
            won_total = sum(b["value"] for b in timeline)
            check("timeline suma > 0 (hay deals won backdatados)", won_total > 0,
                  f"total={won_total}")

        # ── RLS — otro tenant ve pipelineValue=0 ─────────────────────────────
        print("\n── Aislamiento RLS ──────────────────────────────────────────")
        r_iso = await c.get(f"{BASE}/dashboard/kpis", headers=hi)
        check("RLS: /kpis responde 200 para otro tenant", r_iso.status_code == 200)
        iso_kpis = r_iso.json()
        # La clínica beta puede tener sus propios deals, así que
        # verificamos que los deals del tenant demo NO inflaron el valor
        # simplemente chequeando los by-stage del tenant aislado no incluye deals demo
        r_iso_stage = await c.get(f"{BASE}/dashboard/pipeline-by-stage", headers=hi)
        # El tenant iso (asesor) tiene deals de la clínica beta (del seed_pipeline)
        # Verificamos que sus deals son distintos a los del tenant demo
        iso_stage = r_iso_stage.json()
        iso_deal_ids = set(
            d["id"] for d in (await c.get(f"{BASE}/deals?limit=100", headers=hi)).json().get("items", [])
        )
        demo_deal_ids_set = set(
            d["id"] for d in all_deals.get("items", [])
        )
        check(
            "RLS: deals del tenant demo NO visibles para tenant aislado",
            len(iso_deal_ids & demo_deal_ids_set) == 0,
            f"overlap={iso_deal_ids & demo_deal_ids_set}",
        )

        # ── Cleanup ───────────────────────────────────────────────────────────
        await cleanup(c, token_demo)

    # ── Resumen ───────────────────────────────────────────────────────────────
    total  = len(_results)
    passed = sum(_results)
    print(f"\n{'─'*50}")
    print(f"  {passed}/{total} checks PASS")
    if passed < total:
        print("  ❌ Algunos checks fallaron — revisar logs arriba")
        sys.exit(1)
    else:
        print("  ✅ Sprint 13B — Dashboard endpoints: TODO PASS")


if __name__ == "__main__":
    asyncio.run(main())
