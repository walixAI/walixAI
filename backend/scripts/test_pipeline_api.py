"""Test suite for /api/deals + /api/pipeline endpoints.

Adaptado de la suite original de /api/opportunities (eliminada en Etapa 3).
Crea datos de prueba en la DB real (tenant de la clínica seed), corre cada
caso y limpia al final. Requiere que el servidor esté corriendo en
localhost:8000.

Uso:
    cd backend
    .venv/bin/python scripts/test_pipeline_api.py

Cobertura:
  TEST 1  GET  /pipeline/board — agrupa leads por etapa
  TEST 2  POST /deals — crear deal con lead
  TEST 3  POST /deals con lead soft-deleted → 422
  TEST 4  GET  /deals — lista con filtros is_won/is_lost
  TEST 5  GET  /deals/{id} + GET /deals/{id}/stage-history
  TEST 6  PATCH /deals/{id} — lost_reason inválido → 422
  TEST 7  PATCH /deals/{id} — marcar perdido con lost_reason
  TEST 8  OMITIDO — /deals/forecast sin equivalente en el API actual
  TEST 9  OMITIDO — /deals/bulk/stage sin equivalente en el API actual
  TEST 10 OMITIDO — /deals/export.csv sin equivalente en el API actual
  TEST 11 DELETE /deals/{id} → 204
  TEST 12 OMITIDO — /deals/stale sin equivalente en el API actual
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.deal import Deal
from app.models.lead import Lead, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch, Tenant
from app.models.user import User

BASE = "http://localhost:8000/api"
LOGIN_EMAIL = "owner@clinica.com"
LOGIN_PASSWORD = "walix2026"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    results.append((name, condition, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


# ── Auth ───────────────────────────────────────────────────────────────────────

async def get_token(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{BASE}/auth/login", json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


# ── Setup: carga datos del tenant seed ────────────────────────────────────────

async def load_seed_context() -> dict:
    """Devuelve tenant_id, branch_id, stage activa, lost_stage, won_stage, lead_id."""
    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.email == "admin@clinica.com")
        )).scalar_one_or_none()
        if not tenant:
            raise RuntimeError("Tenant seed no encontrado — corre scripts/seed.py primero")

        branch = (await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id, Branch.is_active.is_(True))
            .limit(1)
        )).scalar_one_or_none()
        if not branch:
            raise RuntimeError("No hay branch activa para el tenant seed")

        stages = (await db.execute(
            select(PipelineStage).where(
                PipelineStage.branch_id == branch.id,
                PipelineStage.is_active.is_(True),
            ).order_by(PipelineStage.order_index)
        )).scalars().all()

        regular_stage = next((s for s in stages if not s.is_won and not s.is_lost), None)
        won_stage = next((s for s in stages if s.is_won), None)
        lost_stage = next((s for s in stages if s.is_lost), None)

        # Lead activo de prueba
        lead = Lead(
            branch_id=branch.id,
            tenant_id=tenant.id,
            name="Lead Pipeline Test",
            wa_phone=f"521555{uuid.uuid4().int % 10000000:07d}",
            status=LeadStatus.NUEVO,
        )
        db.add(lead)

        # Lead soft-deleted de prueba
        deleted_lead = Lead(
            branch_id=branch.id,
            tenant_id=tenant.id,
            name="Lead Eliminado Test",
            wa_phone=f"521556{uuid.uuid4().int % 10000000:07d}",
            status=LeadStatus.PERDIDO,
            deleted_at=datetime.now(timezone.utc),
        )
        db.add(deleted_lead)

        await db.flush()
        lead_id = lead.id
        deleted_lead_id = deleted_lead.id
        await db.commit()

        return {
            "tenant_id": str(tenant.id),
            "branch_id": str(branch.id),
            "regular_stage_id": str(regular_stage.id) if regular_stage else None,
            "won_stage_id": str(won_stage.id) if won_stage else None,
            "lost_stage_id": str(lost_stage.id) if lost_stage else None,
            "lead_id": str(lead_id),
            "deleted_lead_id": str(deleted_lead_id),
        }


# ── Cleanup ────────────────────────────────────────────────────────────────────

_created_deal_ids: list[str] = []
_created_lead_ids: list[str] = []


async def cleanup(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        for deal_id in _created_deal_ids:
            deal = await db.get(Deal, uuid.UUID(deal_id))
            if deal:
                await db.delete(deal)
        for lead_id in _created_lead_ids:
            lead = await db.get(Lead, uuid.UUID(lead_id))
            if lead:
                await db.delete(lead)
        # Cleanup test leads by name
        for name in ["Lead Pipeline Test", "Lead Eliminado Test"]:
            rows = (await db.execute(
                select(Lead).where(Lead.name == name, Lead.tenant_id == uuid.UUID(ctx["tenant_id"]))
            )).scalars().all()
            for lead in rows:
                await db.delete(lead)
        await db.commit()


# ── Tests ──────────────────────────────────────────────────────────────────────

async def run_tests() -> None:
    ctx = await load_seed_context()
    print(f"\nContext: branch={ctx['branch_id'][:8]}... regular_stage={ctx['regular_stage_id'] and ctx['regular_stage_id'][:8]}...")

    async with httpx.AsyncClient(timeout=15) as client:
        token = await get_token(client)
        h = {"Authorization": f"Bearer {token}"}

        print("\n── TEST 1: GET /pipeline/board agrupa leads por etapa ──")
        r = await client.get(f"{BASE}/pipeline/board", headers=h,
                             params={"branch_id": ctx["branch_id"]})
        check("board HTTP 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            data = r.json()
            check("board tiene 'stages'", "stages" in data)
            if data["stages"]:
                s = data["stages"][0]
                check("stage tiene 'leads'", "leads" in s)
                check("stage tiene 'total'", "total" in s)
                check("stage tiene 'is_won'", "is_won" in s)
                check("stage tiene 'is_lost'", "is_lost" in s)

        print("\n── TEST 2: POST /deals — crear deal con lead ──")
        r = await client.post(f"{BASE}/deals", headers=h, json={
            "title": "Deal Test A",
            "lead_id": ctx["lead_id"],
            "pipeline_stage_id": ctx["regular_stage_id"],
            "amount": "15000.00",
            "expected_close_date": str(date.today()),
        })
        check("crear deal HTTP 201", r.status_code == 201, str(r.status_code))
        deal_a_id: str | None = None
        if r.status_code == 201:
            deal_a = r.json()
            deal_a_id = deal_a["id"]
            _created_deal_ids.append(deal_a_id)
            check("deal tiene title", deal_a.get("title") == "Deal Test A")
            check("is_won=False", deal_a.get("is_won") is False)
            check("is_lost=False", deal_a.get("is_lost") is False)
            check("amount=15000", float(deal_a.get("amount", 0)) == 15000.0)

        print("\n── TEST 3: POST /deals con lead soft-deleted → 422 ──")
        r = await client.post(f"{BASE}/deals", headers=h, json={
            "title": "Deal Lead Eliminado",
            "lead_id": ctx["deleted_lead_id"],
            "pipeline_stage_id": ctx["regular_stage_id"],
        })
        check("lead soft-deleted → 422", r.status_code == 422, str(r.status_code))

        print("\n── TEST 4: GET /deals — lista con filtros ──")
        r = await client.get(f"{BASE}/deals", headers=h,
                             params={"is_won": "false", "is_lost": "false"})
        check("lista HTTP 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            data = r.json()
            check("lista tiene 'items' y 'total'", "items" in data and "total" in data)
            if deal_a_id:
                ids = [item["id"] for item in data.get("items", [])]
                check("deal_a aparece en la lista", deal_a_id in ids)

        print("\n── TEST 5: GET /deals/{id} + stage-history ──")
        if deal_a_id:
            r = await client.get(f"{BASE}/deals/{deal_a_id}", headers=h)
            check("detalle deal HTTP 200", r.status_code == 200, str(r.status_code))
            if r.status_code == 200:
                detail = r.json()
                check("detalle tiene 'id'", "id" in detail)
                check("detalle tiene 'pipeline_stage_id'", "pipeline_stage_id" in detail)
                check("detalle tiene 'is_won'", "is_won" in detail)

            r2 = await client.get(f"{BASE}/deals/{deal_a_id}/stage-history", headers=h)
            check("stage-history HTTP 200", r2.status_code == 200, str(r2.status_code))
            if r2.status_code == 200:
                check("stage-history es lista", isinstance(r2.json(), list))

        print("\n── TEST 6: PATCH /deals/{id} — lost_reason inválido → 422 ──")
        if deal_a_id:
            r = await client.patch(f"{BASE}/deals/{deal_a_id}", headers=h,
                                   json={"lost_reason": "razon_no_valida"})
            check("lost_reason inválido → 422", r.status_code == 422, str(r.status_code))

        print("\n── TEST 7: PATCH /deals/{id} — marcar perdido ──")
        if deal_a_id and ctx["lost_stage_id"]:
            r = await client.patch(f"{BASE}/deals/{deal_a_id}", headers=h, json={
                "is_lost": True,
                "lost_reason": "price",
                "pipeline_stage_id": ctx["lost_stage_id"],
            })
            check("marcar perdido HTTP 200", r.status_code == 200, str(r.status_code))
            if r.status_code == 200:
                data = r.json()
                check("is_lost=True", data.get("is_lost") is True)
                check("lost_reason=price", data.get("lost_reason") == "price")
        elif not ctx["lost_stage_id"]:
            print("  [SKIP] Sin etapa is_lost configurada")

        # TEST 8: forecast — OMITIDO (sin equivalente en /api/deals actual)
        # TEST 9: bulk/stage — OMITIDO (sin equivalente en /api/deals actual)
        # TEST 10: export.csv — OMITIDO (sin equivalente en /api/deals actual)

        print("\n── TEST 11: DELETE /deals/{id} → 204 ──")
        # Crear un deal fresco para borrar (deal_a puede estar ya marcado perdido)
        r = await client.post(f"{BASE}/deals", headers=h, json={
            "title": "Deal Para Borrar",
            "lead_id": ctx["lead_id"],
            "pipeline_stage_id": ctx["regular_stage_id"],
        })
        deal_del_id: str | None = None
        if r.status_code == 201:
            deal_del_id = r.json()["id"]
            _created_deal_ids.append(deal_del_id)

        if deal_del_id:
            r = await client.delete(f"{BASE}/deals/{deal_del_id}", headers=h)
            check("delete HTTP 204", r.status_code == 204, str(r.status_code))
            r2 = await client.get(f"{BASE}/deals/{deal_del_id}", headers=h)
            check("deal eliminado → 404", r2.status_code == 404, str(r2.status_code))
            if deal_del_id in _created_deal_ids:
                _created_deal_ids.remove(deal_del_id)  # ya borrado vía API

        # TEST 12: stale — OMITIDO (sin equivalente en /api/deals actual)

    await cleanup(ctx)


# ── main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 60)
    print("  test_pipeline_api.py — Deals + Pipeline board")
    print("=" * 60)

    try:
        await run_tests()
    except Exception as exc:
        print(f"\n\033[31mERROR no capturado: {exc}\033[0m")
        import traceback
        traceback.print_exc()

    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)

    print("\n" + "=" * 60)
    print(f"  Resultado: {passed}/{total} PASS  ·  {failed} FAIL")
    print("=" * 60)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
