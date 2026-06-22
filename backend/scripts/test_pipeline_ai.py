"""Test suite for /api/opportunities AI endpoints.

Uses httpx.AsyncClient with ASGITransport (in-process) so unittest.mock.patch
actually intercepts the Haiku client that runs inside the request handler.
Seed data writes directly to the real DB; HTTP calls go through the FastAPI app.

Usage:
    cd backend
    .venv/bin/python scripts/test_pipeline_ai.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

import httpx
from httpx import ASGITransport
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis import redis_client as _redis
from app.models.lead import Lead, LeadStatus
from app.models.opportunity import Opportunity
from app.models.opportunity_activity import OpportunityActivity
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch, Tenant

# Import FastAPI app for in-process transport (mocks work in same process)
from app.main import app  # noqa: E402  (imported after sys.path tweak)

BASE = "/api"
LOGIN_EMAIL = "owner@clinica.com"
LOGIN_PASSWORD = "walix2026"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    sym = PASS if condition else FAIL
    results.append((name, condition, detail))
    print(f"  [{sym}] {name}" + (f" — {detail}" if detail else ""))


# ── Seed helpers ───────────────────────────────────────────────────────────────

async def load_seed_context() -> dict:
    """Return tenant_id, branch_id, and create a test opp in the real DB."""
    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.email == "admin@clinica.com")
        )).scalar_one_or_none()
        if not tenant:
            raise RuntimeError("Tenant seed no encontrado — corre scripts/seed.py primero")

        branch = (await db.execute(
            select(Branch)
            .where(Branch.tenant_id == tenant.id, Branch.is_active.is_(True))
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

        lead = Lead(
            branch_id=branch.id,
            tenant_id=tenant.id,
            name="Test AI Lead",
            wa_phone=f"521599{uuid.uuid4().int % 10000000:07d}",
            status=LeadStatus.NUEVO,
        )
        db.add(lead)
        await db.flush()

        opp = Opportunity(
            tenant_id=tenant.id,
            branch_id=branch.id,
            lead_id=lead.id,
            stage_id=regular_stage.id if regular_stage else None,
            title="AI Test Oportunidad",
            amount=50000,
            currency="MXN",
            probability=40,
            status="open",
            stage_entered_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc),
            notes="Cliente interesado en plan premium.",
        )
        db.add(opp)
        await db.flush()

        opp_id = str(opp.id)
        lead_id = str(lead.id)

        if regular_stage and regular_stage.probability_default is None:
            regular_stage.probability_default = 40

        await db.commit()
        return {
            "tenant_id": str(tenant.id),
            "branch_id": str(branch.id),
            "opp_id": opp_id,
            "lead_id": lead_id,
        }


_created_opp_ids: list[str] = []
_created_lead_ids: list[str] = []


async def cleanup(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        for oid in _created_opp_ids:
            try:
                o = await db.get(Opportunity, uuid.UUID(oid))
                if o:
                    acts = (await db.execute(
                        select(OpportunityActivity)
                        .where(OpportunityActivity.opportunity_id == o.id)
                    )).scalars().all()
                    for a in acts:
                        await db.delete(a)
                    await db.delete(o)
            except Exception as e:
                print(f"  [WARN] cleanup opp {oid}: {e}")
        for lid in _created_lead_ids:
            try:
                l = await db.get(Lead, uuid.UUID(lid))
                if l:
                    await db.delete(l)
            except Exception as e:
                print(f"  [WARN] cleanup lead {lid}: {e}")
        rows = (await db.execute(select(Lead).where(Lead.name == "Test AI Lead"))).scalars().all()
        for l in rows:
            await db.delete(l)
        await db.commit()


# ── Mock factory ───────────────────────────────────────────────────────────────

def _haiku_mock(payload: dict) -> AsyncMock:
    """AsyncMock that mimics anthropic.messages.create() return value."""
    content = MagicMock()
    content.text = json.dumps(payload)
    resp = MagicMock()
    resp.content = [content]
    return AsyncMock(return_value=resp)


# ── Tests ──────────────────────────────────────────────────────────────────────

async def run_tests(ctx: dict) -> None:
    opp_id = ctx["opp_id"]
    branch_id = ctx["branch_id"]
    cache_key = f"opp:insights:{branch_id}"

    # In-process client — patches work because handler runs in this process
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as client:

        # Auth (in-process login against real DB)
        r = await client.post(f"{BASE}/auth/login",
                              json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD})
        assert r.status_code == 200, f"Login failed: {r.text}"
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        # ── T1: next-step OK ──────────────────────────────────────────────────
        print("\n── T1: POST /{opp_id}/ai/next-step — Haiku returns valid JSON ──")
        t1_payload = {
            "text": "Llamar al cliente para confirmar propuesta",
            "reasoning": "No hay actividad en 5 días",
            "urgency": "high",
        }
        with patch("app.api.opportunities_ai._anthropic.messages.create",
                   new=_haiku_mock(t1_payload)):
            r = await client.post(f"{BASE}/opportunities/{opp_id}/ai/next-step", headers=h)

        check("T1 HTTP 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            body = r.json()
            check("T1 text == mocked", body.get("text") == t1_payload["text"], repr(body.get("text")))
            check("T1 urgency=high", body.get("urgency") == "high", body.get("urgency"))
            check("T1 reasoning presente", body.get("reasoning") is not None)

        async with AsyncSessionLocal() as db:
            opp = await db.get(Opportunity, uuid.UUID(opp_id))
            check("T1 ai_suggestion guardado en DB",
                  opp is not None and opp.ai_suggestion == t1_payload["text"],
                  repr(opp.ai_suggestion if opp else None))
            check("T1 urgency_score=85 (high)",
                  opp is not None and opp.urgency_score == 85,
                  str(opp.urgency_score if opp else None))

        # ── T2: next-step fallback ────────────────────────────────────────────
        print("\n── T2: POST /{opp_id}/ai/next-step — Haiku raises Exception ──")
        with patch("app.api.opportunities_ai._anthropic.messages.create",
                   new=AsyncMock(side_effect=Exception("AI down"))):
            r = await client.post(f"{BASE}/opportunities/{opp_id}/ai/next-step", headers=h)

        check("T2 HTTP 200 (graceful fallback)", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            body = r.json()
            check("T2 text=null", body.get("text") is None, repr(body.get("text")))
            check("T2 reasoning=null", body.get("reasoning") is None)
            check("T2 urgency=null", body.get("urgency") is None)

        # ── T3: probability OK ────────────────────────────────────────────────
        print("\n── T3: POST /{opp_id}/ai/probability — Haiku returns suggestion ──")
        t3_payload = {"suggested": 80, "signals": ["Monto alto", "Cierre próximo", "Lead calificado"]}
        with patch("app.api.opportunities_ai._anthropic.messages.create",
                   new=_haiku_mock(t3_payload)):
            r = await client.post(f"{BASE}/opportunities/{opp_id}/ai/probability", headers=h)

        check("T3 HTTP 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            body = r.json()
            check("T3 suggested=80", body.get("suggested") == 80, str(body.get("suggested")))
            check("T3 signals es lista", isinstance(body.get("signals"), list),
                  str(body.get("signals")))
            check("T3 current matches opp.probability", body.get("current") == 40,
                  str(body.get("current")))

        async with AsyncSessionLocal() as db:
            opp = await db.get(Opportunity, uuid.UUID(opp_id))
            check("T3 probability NO cambió en DB",
                  opp is not None and opp.probability == 40,
                  str(opp.probability if opp else None))

        # ── T4: probability fallback ──────────────────────────────────────────
        print("\n── T4: POST /{opp_id}/ai/probability — Haiku raises Exception ──")
        with patch("app.api.opportunities_ai._anthropic.messages.create",
                   new=AsyncMock(side_effect=Exception("timeout"))):
            r = await client.post(f"{BASE}/opportunities/{opp_id}/ai/probability", headers=h)

        check("T4 HTTP 200 (fallback)", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            body = r.json()
            check("T4 suggested = current_prob (40)", body.get("suggested") == 40,
                  str(body.get("suggested")))
            check("T4 signals=[]", body.get("signals") == [], str(body.get("signals")))

        # ── T5: insights OK + cached ──────────────────────────────────────────
        print("\n── T5: POST /ai/insights — Haiku returns full response, caches to Redis ──")
        await _redis.delete(cache_key)

        t5_payload = {
            "summary": "Pipeline con health score 85/100, buena actividad general.",
            "risks": [
                {"title": "Oportunidades estancadas", "severity": "high",
                 "description": "20% de opps sin actividad en 14+ días"},
            ],
            "recommendations": [
                {"title": "Revisar oportunidades estancadas", "impact": "high",
                 "action": "Contactar 3 leads sin actividad esta semana"},
            ],
        }
        mock_insights = _haiku_mock(t5_payload)
        with patch("app.api.opportunities_ai._anthropic.messages.create", new=mock_insights):
            r = await client.post(f"{BASE}/opportunities/ai/insights",
                                  headers=h, json={"branch_id": branch_id})

        check("T5 HTTP 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            body = r.json()
            check("T5 health_score es int", isinstance(body.get("health_score"), int),
                  str(body.get("health_score")))
            check("T5 summary presente", bool(body.get("summary")), str(body.get("summary", ""))[:60])
            check("T5 risks es lista", isinstance(body.get("risks"), list))
            check("T5 recommendations es lista", isinstance(body.get("recommendations"), list))

        cached_raw = await _redis.get(cache_key)
        check("T5 resultado cacheado en Redis", cached_raw is not None,
              "(cache miss)" if cached_raw is None else "cache hit")

        # ── T6: insights cache hit — Haiku NOT called again ───────────────────
        print("\n── T6: POST /ai/insights — cache hit, Haiku no llamado ──")
        mock_insights_2 = AsyncMock(side_effect=Exception("should not be called"))
        with patch("app.api.opportunities_ai._anthropic.messages.create", new=mock_insights_2):
            r2 = await client.post(f"{BASE}/opportunities/ai/insights",
                                   headers=h, json={"branch_id": branch_id})

        check("T6 HTTP 200 (from cache)", r2.status_code == 200, str(r2.status_code))
        check("T6 Haiku NO fue llamado de nuevo", mock_insights_2.call_count == 0,
              f"calls={mock_insights_2.call_count}")
        if r.status_code == 200 and r2.status_code == 200:
            check("T6 health_score idéntico",
                  r.json().get("health_score") == r2.json().get("health_score"),
                  f"{r.json().get('health_score')} vs {r2.json().get('health_score')}")

        # ── T7: insights fallback (no cache + Haiku fails) ────────────────────
        print("\n── T7: POST /ai/insights — Redis clear + Haiku fails → fallback ──")
        await _redis.delete(cache_key)

        with patch("app.api.opportunities_ai._anthropic.messages.create",
                   new=AsyncMock(side_effect=Exception("haiku down"))):
            r3 = await client.post(f"{BASE}/opportunities/ai/insights",
                                   headers=h, json={"branch_id": branch_id})

        check("T7 HTTP 200 (fallback)", r3.status_code == 200, str(r3.status_code))
        if r3.status_code == 200:
            body3 = r3.json()
            check("T7 health_score calculado (int)", isinstance(body3.get("health_score"), int),
                  str(body3.get("health_score")))
            check("T7 risks=[]", body3.get("risks") == [], str(body3.get("risks")))
            check("T7 recommendations=[]", body3.get("recommendations") == [],
                  str(body3.get("recommendations")))
            check("T7 summary fallback",
                  body3.get("summary") == "Análisis no disponible.",
                  repr(body3.get("summary")))
        await _redis.delete(cache_key)

        # ── T8: bulk-suggestions → 202 queued ────────────────────────────────
        print("\n── T8: POST /ai/bulk-suggestions — Celery .delay() mocked → 202 ──")
        mock_task = MagicMock()
        with patch("app.tasks.opp_ai_tasks.generate_bulk_suggestions", new=mock_task):
            r4 = await client.post(f"{BASE}/opportunities/ai/bulk-suggestions",
                                   headers=h, json={"branch_id": branch_id})

        check("T8 HTTP 202", r4.status_code == 202, str(r4.status_code))
        if r4.status_code == 202:
            body4 = r4.json()
            check("T8 status=queued", body4.get("status") == "queued", str(body4.get("status")))
            check("T8 branch_id correcto", body4.get("branch_id") == branch_id,
                  str(body4.get("branch_id")))
        check("T8 delay() llamado 1 vez", mock_task.delay.call_count == 1,
              f"calls={mock_task.delay.call_count}")


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 60)
    print("  test_pipeline_ai.py — AI Layer de Oportunidades")
    print("=" * 60)

    ctx: dict = {}
    try:
        ctx = await load_seed_context()
        _created_opp_ids.append(ctx["opp_id"])
        _created_lead_ids.append(ctx["lead_id"])
        print(f"\nContext: branch={ctx['branch_id'][:8]}... opp={ctx['opp_id'][:8]}...")
        await run_tests(ctx)
    except Exception as exc:
        print(f"\n\033[31mERROR no capturado: {exc}\033[0m")
        import traceback
        traceback.print_exc()
    finally:
        if ctx:
            await cleanup(ctx)

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
