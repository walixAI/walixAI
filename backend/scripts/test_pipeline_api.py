"""Test suite for /api/opportunities endpoints.

Crea datos de prueba en la DB real (tenant de la clínica seed), corre cada caso,
y limpia al final. Requiere que el servidor esté corriendo en localhost:8000.

Uso:
    cd backend
    .venv/bin/python scripts/test_pipeline_api.py
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
from app.models.lead import Lead, LeadStatus
from app.models.opportunity import Opportunity
from app.models.opportunity_activity import OpportunityActivity
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

        # Encontrar o crear etapas de prueba
        regular_stage = next((s for s in stages if not s.is_won and not s.is_lost), None)
        won_stage = next((s for s in stages if s.is_won), None)
        lost_stage = next((s for s in stages if s.is_lost), None)

        # Crear un lead activo de prueba
        lead = Lead(
            branch_id=branch.id,
            tenant_id=tenant.id,
            name="Lead Pipeline Test",
            wa_phone=f"521555{uuid.uuid4().int % 10000000:07d}",
            status=LeadStatus.NUEVO,
        )
        db.add(lead)

        # Crear un lead soft-deleted de prueba
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

        # Set probability_default on regular_stage for inherit test
        if regular_stage:
            regular_stage.probability_default = 30

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

_created_opp_ids: list[str] = []
_created_lead_ids: list[str] = []


async def cleanup(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        for opp_id in _created_opp_ids:
            opp = await db.get(Opportunity, uuid.UUID(opp_id))
            if opp:
                await db.delete(opp)
        for lead_id in _created_lead_ids:
            lead = await db.get(Lead, uuid.UUID(lead_id))
            if lead:
                await db.delete(lead)
        # Cleanup test leads by name
        for name in ["Lead Pipeline Test", "Lead Eliminado Test"]:
            rows = (await db.execute(
                select(Lead).where(Lead.name == name, Lead.tenant_id == uuid.UUID(ctx["tenant_id"]))
            )).scalars().all()
            for l in rows:
                await db.delete(l)
        await db.commit()


# ── Tests ──────────────────────────────────────────────────────────────────────

async def run_tests() -> None:
    ctx = await load_seed_context()
    print(f"\nContext: branch={ctx['branch_id'][:8]}... regular_stage={ctx['regular_stage_id'] and ctx['regular_stage_id'][:8]}...")

    async with httpx.AsyncClient(timeout=15) as client:
        token = await get_token(client)
        h = {"Authorization": f"Bearer {token}"}

        print("\n── TEST 1: GET /board agrupa por etapa ──")
        r = await client.get(f"{BASE}/opportunities/board", headers=h,
                             params={"branch_id": ctx["branch_id"]})
        check("board HTTP 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            data = r.json()
            check("board tiene 'stages'", "stages" in data)
            check("board tiene 'currency'", "currency" in data)
            if data["stages"]:
                s = data["stages"][0]
                check("stage tiene 'opportunities'", "opportunities" in s)
                check("stage tiene 'total_amount'", "total_amount" in s)
                check("stage tiene 'total'", "total" in s)
                check("stage tiene 'probability_default'", "probability_default" in s)

        print("\n── TEST 2: POST / crear oportunidad con lead ──")
        r = await client.post(f"{BASE}/opportunities", headers=h, json={
            "title": "Oportunidad Test A",
            "lead_id": ctx["lead_id"],
            "stage_id": ctx["regular_stage_id"],
            "branch_id": ctx["branch_id"],
            "amount": "15000.00",
            "currency": "MXN",
            "close_date": str(date.today()),
        })
        check("crear oportunidad HTTP 201", r.status_code == 201, str(r.status_code))
        opp_a_id: str | None = None
        if r.status_code == 201:
            opp_a = r.json()
            opp_a_id = opp_a["id"]
            _created_opp_ids.append(opp_a_id)
            check("opp tiene title", opp_a.get("title") == "Oportunidad Test A")
            check("probability heredada de etapa (30)", opp_a.get("probability") == 30)
            check("status=open", opp_a.get("status") == "open")
            check("currency en mayúsculas", opp_a.get("currency") == "MXN")

        print("\n── TEST 3: POST / con lead soft-deleted → 409 ──")
        r = await client.post(f"{BASE}/opportunities", headers=h, json={
            "title": "Oportunidad Lead Eliminado",
            "lead_id": ctx["deleted_lead_id"],
            "stage_id": ctx["regular_stage_id"],
            "branch_id": ctx["branch_id"],
        })
        check("lead soft-deleted → 409", r.status_code == 409, str(r.status_code))
        if r.status_code == 409:
            check("mensaje de error en español", "eliminado" in r.json().get("detail", "").lower())

        print("\n── TEST 4: GET / lista con filtros ──")
        r = await client.get(f"{BASE}/opportunities", headers=h,
                             params={"branch_id": ctx["branch_id"], "status": "open"})
        check("lista HTTP 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            data = r.json()
            check("lista tiene 'items' y 'total'", "items" in data and "total" in data)

        print("\n── TEST 5: GET /{id} detalle con historial ──")
        if opp_a_id:
            r = await client.get(f"{BASE}/opportunities/{opp_a_id}", headers=h)
            check("detalle HTTP 200", r.status_code == 200, str(r.status_code))
            if r.status_code == 200:
                detail = r.json()
                check("detalle tiene 'activities'", "activities" in detail)
                check("detalle tiene 'history'", "history" in detail)
                check("actividad 'created' registrada",
                      any(a["type"] == "created" for a in detail.get("activities", [])))

        print("\n── TEST 6: PATCH /{id}/stage → etapa lost → 422 requires_reason ──")
        if opp_a_id and ctx["lost_stage_id"]:
            r = await client.patch(
                f"{BASE}/opportunities/{opp_a_id}/stage",
                headers=h,
                json={"stage_id": ctx["lost_stage_id"]},
            )
            check("stage a lost → 422", r.status_code == 422, str(r.status_code))
            if r.status_code == 422:
                detail = r.json().get("detail", {})
                check("requires_reason=true en detail",
                      (isinstance(detail, dict) and detail.get("requires_reason") is True)
                      or (isinstance(detail, list) and any(
                          isinstance(e, dict) and e.get("requires_reason") for e in detail
                      )),
                      str(detail))
        elif not ctx["lost_stage_id"]:
            print("  [SKIP] Sin etapa is_lost configurada")

        print("\n── TEST 7: POST /{id}/lost completa ──")
        if opp_a_id and ctx["lost_stage_id"]:
            r = await client.post(
                f"{BASE}/opportunities/{opp_a_id}/lost",
                headers=h,
                json={"lost_reason": "Precio muy alto", "reason_code": "price"},
            )
            check("mark_lost HTTP 200", r.status_code == 200, str(r.status_code))
            if r.status_code == 200:
                data = r.json()
                check("status=lost", data.get("status") == "lost")
                check("lost_reason guardado", data.get("lost_reason") == "Precio muy alto")
                check("lost_at tiene valor", data.get("lost_at") is not None)
        elif not ctx["lost_stage_id"]:
            print("  [SKIP] Sin etapa is_lost configurada")

        print("\n── TEST 8: weighted_total correcto ──")
        # Crear oportunidad con monto y probabilidad conocidos
        r = await client.post(f"{BASE}/opportunities", headers=h, json={
            "title": "Opp Forecast Test",
            "stage_id": ctx["regular_stage_id"],
            "branch_id": ctx["branch_id"],
            "amount": "10000.00",
            "probability": 50,
        })
        opp_b_id: str | None = None
        if r.status_code == 201:
            opp_b_id = r.json()["id"]
            _created_opp_ids.append(opp_b_id)

        r = await client.get(f"{BASE}/opportunities/forecast", headers=h,
                             params={"branch_id": ctx["branch_id"]})
        check("forecast HTTP 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            fc = r.json()
            check("forecast tiene pipeline_total", "pipeline_total" in fc)
            check("forecast tiene weighted_total", "weighted_total" in fc)
            check("forecast tiene active_count", "active_count" in fc)
            check("forecast tiene trend", fc.get("trend") in ("up", "down", "flat"))
            if opp_b_id:
                wt = float(fc.get("weighted_total", 0))
                check("weighted_total >= 5000 (10000 * 0.5)", wt >= 5000, f"wt={wt}")

        print("\n── TEST 9: bulk/stage ──")
        # Crear dos oportunidades nuevas para mover en bulk
        opp_bulk_ids: list[str] = []
        for title in ["Bulk A", "Bulk B"]:
            r = await client.post(f"{BASE}/opportunities", headers=h, json={
                "title": title,
                "stage_id": ctx["regular_stage_id"],
                "branch_id": ctx["branch_id"],
                "amount": "1000.00",
            })
            if r.status_code == 201:
                bid = r.json()["id"]
                opp_bulk_ids.append(bid)
                _created_opp_ids.append(bid)

        if opp_bulk_ids and ctx["regular_stage_id"]:
            r = await client.post(f"{BASE}/opportunities/bulk/stage", headers=h, json={
                "ids": opp_bulk_ids,
                "stage_id": ctx["regular_stage_id"],
            })
            check("bulk/stage HTTP 200", r.status_code == 200, str(r.status_code))
            if r.status_code == 200:
                items = r.json()
                check(f"bulk/stage retorna {len(opp_bulk_ids)} items",
                      len(items) == len(opp_bulk_ids), str(len(items)))

        print("\n── TEST 10: export.csv 200 utf-8-sig ──")
        r = await client.get(
            f"{BASE}/opportunities/export.csv",
            headers=h,
            params={"branch_id": ctx["branch_id"]},
        )
        check("export.csv HTTP 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            content_type = r.headers.get("content-type", "")
            check("content-type es text/csv", "text/csv" in content_type, content_type)
            content = r.content
            check("empieza con BOM utf-8-sig (\\xef\\xbb\\xbf)",
                  content[:3] == b"\xef\xbb\xbf", repr(content[:3]))
            # Decodificar y verificar encabezado
            text = content.decode("utf-8-sig")
            first_line = text.splitlines()[0] if text.strip() else ""
            check("encabezado CSV correcto",
                  "Oportunidad" in first_line and "Contacto" in first_line,
                  repr(first_line[:80]))

        print("\n── TEST 11: DELETE /{id} soft-delete ──")
        if opp_b_id:
            r = await client.delete(f"{BASE}/opportunities/{opp_b_id}", headers=h)
            check("delete HTTP 204", r.status_code == 204, str(r.status_code))
            # Verificar que no aparece en lista
            r2 = await client.get(f"{BASE}/opportunities/{opp_b_id}", headers=h)
            check("opp eliminada → 404", r2.status_code == 404, str(r2.status_code))
            opp_b_id = None  # ya eliminada, no limpiar de nuevo

        print("\n── TEST 12: GET /stale ──")
        r = await client.get(f"{BASE}/opportunities/stale", headers=h,
                             params={"branch_id": ctx["branch_id"], "days": "10"})
        check("stale HTTP 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            data = r.json()
            check("stale tiene count, total_amount, items",
                  "count" in data and "total_amount" in data and "items" in data)

    await cleanup(ctx)


# ── main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 60)
    print("  test_pipeline_api.py — Módulo Oportunidades")
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
