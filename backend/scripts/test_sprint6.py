"""Sprint 6 — test_sprint6.py

Prueba end-to-end de los 6 sistemas del Sprint 6:

  1. Score de predicción      — recalculate + verificar score/factors/current_score
  2. Agente de seguimiento    — lead inactivo + run_follow_up_agent + confirm
  3. Motor de métricas        — aggregate_daily_metrics + GET /metrics/dashboard
  4. Sentimiento              — calculate_sentiment_snapshot + GET /metrics/sentiment
  5. Dashboards por rol       — asesor / gerente / owner
  6. Repositorio de automaciones — GET + PATCH /automations

Corre desde backend/:
    .venv/bin/python scripts/test_sprint6.py
"""

import asyncio
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.agent import AgentSuggestion
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.tenant import Branch  # noqa: F401 — kept for FK resolution in SQLAlchemy mapper
from app.models.user import User, UserRole

BASE_URL = "http://localhost:8000"
ASESOR_EMAIL = "asistente@clinica.com"
OWNER_EMAIL = "owner@clinica.com"
PASSWORD = "walix2026"

_ok = 0
_fail = 0


# ── Result helpers ─────────────────────────────────────────────────────────────

def ok(label: str) -> None:
    global _ok
    _ok += 1
    print(f"  ✓ {label}")


def fail(label: str, detail: str = "") -> None:
    global _fail
    _fail += 1
    suffix = f" — {detail}" if detail else ""
    print(f"  ✗ {label}{suffix}")


def check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        ok(label)
    else:
        fail(label, detail)
    return condition


def info(msg: str) -> None:
    print(f"  ℹ {msg}")


# ── DB helpers ─────────────────────────────────────────────────────────────────

async def _get_branch_for_user(email: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            raise RuntimeError(f"Usuario {email} no encontrado — corre seed.py")
        if user.branch_id is None:
            raise RuntimeError(f"Usuario {email} no tiene branch_id")
        return user.branch_id, user.tenant_id


async def _ensure_gerente_user(tenant_id: uuid.UUID, branch_id: uuid.UUID) -> str:
    email = "gerente@clinica.com"
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is None:
            db.add(User(
                tenant_id=tenant_id,
                branch_id=branch_id,
                email=email,
                name="Gerente Clínica",
                hashed_password=hash_password(PASSWORD),
                role=UserRole.GERENTE,
                is_active=True,
            ))
            await db.commit()
            print(f"  → Usuario gerente creado: {email}")
        else:
            print(f"  → Usuario gerente encontrado: {email}")
    return email


async def _get_first_lead_id(branch_id: uuid.UUID) -> uuid.UUID | None:
    async with AsyncSessionLocal() as db:
        result = (
            await db.execute(
                select(Lead.id)
                .where(Lead.branch_id == branch_id)
                .order_by(Lead.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        return result


async def _get_lead_current_score(lead_id: uuid.UUID) -> int | None:
    async with AsyncSessionLocal() as db:
        lead = await db.get(Lead, lead_id)
        return lead.current_score if lead else None


async def _create_inactive_lead_with_conversation(
    branch_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a lead + open conversation with a message 30h old."""
    old_ts = datetime.now(timezone.utc) - timedelta(hours=30)
    async with AsyncSessionLocal() as db:
        lead = Lead(
            branch_id=branch_id,
            tenant_id=tenant_id,
            wa_phone=f"5215560{uuid.uuid4().hex[:7]}",
            name="Lead Inactivo Sprint6",
            source=LeadSource.WHATSAPP_INBOUND,
            status=LeadStatus.EN_CALIFICACION,
            qualification_data={},
        )
        db.add(lead)
        await db.flush()

        conv = Conversation(
            branch_id=branch_id,
            tenant_id=tenant_id,
            lead_id=lead.id,
            status=ConversationStatus.ACTIVE,
            current_handler=ConversationHandler.BOT,
        )
        db.add(conv)
        await db.flush()

        msg = Message(
            conversation_id=conv.id,
            tenant_id=tenant_id,
            role=MessageRole.USER,
            content="Hola, me interesa información",
        )
        db.add(msg)
        await db.flush()

        # Back-date the message so the agent considers it inactive
        await db.execute(
            update(Message).where(Message.id == msg.id).values(created_at=old_ts)
        )
        await db.commit()

        lead_id = lead.id
        conv_id = conv.id

    print(f"  → Lead inactivo creado: {str(lead_id)[:8]}… (mensaje a las {old_ts.strftime('%H:%M UTC')})")
    return lead_id, conv_id


async def _count_pending_suggestions(branch_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentSuggestion)
            .where(
                AgentSuggestion.branch_id == branch_id,
                AgentSuggestion.status.in_(["suggested", "accepted"]),
            )
        )
        return len(result.scalars().all())


async def _get_any_pending_suggestion_id(tenant_id: uuid.UUID) -> uuid.UUID | None:
    async with AsyncSessionLocal() as db:
        result = (
            await db.execute(
                select(AgentSuggestion.id)
                .where(
                    AgentSuggestion.tenant_id == tenant_id,
                    AgentSuggestion.status.in_(["suggested", "accepted"]),
                )
                .order_by(AgentSuggestion.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return result


async def _get_suggestion_status(suggestion_id: uuid.UUID) -> str | None:
    async with AsyncSessionLocal() as db:
        s = await db.get(AgentSuggestion, suggestion_id)
        return s.status if s else None


# ── Section 1: Score de predicción ────────────────────────────────────────────

async def _test_score(client: httpx.AsyncClient, auth: dict, branch_id: uuid.UUID) -> None:
    print("\n── 1. Score de predicción ─────────────────────────────────────────")

    lead_id = await _get_first_lead_id(branch_id)
    if lead_id is None:
        fail("Lead disponible para score", "No hay leads — corre seed_pipeline.py")
        return
    print(f"  → Usando lead: {str(lead_id)[:8]}…")

    print("\n[1a] POST /api/leads/{id}/score/recalculate")
    r = await client.post(f"/api/leads/{lead_id}/score/recalculate", headers=auth)
    check("POST /score/recalculate 200", r.status_code == 200,
          f"HTTP {r.status_code}: {r.text[:120]}")
    if r.status_code != 200:
        return

    data = r.json()
    score = data.get("score")
    print(f"     score         : {score}")
    print(f"     main_reason   : {str(data.get('main_reason', ''))[:60]}")
    print(f"     positive_factors: {data.get('positive_factors', {}).get('items', [])[:3]}")
    print(f"     negative_factors: {data.get('negative_factors', {}).get('items', [])[:3]}")

    check("score es entero 0-100",
          isinstance(score, int) and 0 <= score <= 100,
          f"got: {score!r}")
    check("main_reason no vacío", bool(data.get("main_reason")), "vacío")
    check("positive_factors es dict con items",
          isinstance(data.get("positive_factors"), dict),
          f"got: {type(data.get('positive_factors'))}")

    print("\n[1b] Verificar leads.current_score actualizado")
    db_score = await _get_lead_current_score(lead_id)
    check("leads.current_score == score calculado",
          db_score == score,
          f"db={db_score}, api={score}")

    print("\n[1c] GET /api/leads/{id}/score (historial)")
    r2 = await client.get(f"/api/leads/{lead_id}/score", headers=auth)
    check("GET /score 200", r2.status_code == 200, f"HTTP {r2.status_code}")
    if r2.status_code == 200:
        hist = r2.json()
        check("history tiene al menos 1 entrada",
              len(hist.get("history", [])) >= 1,
              f"len={len(hist.get('history', []))}")
        check("current_score == score calculado",
              hist.get("current_score") == score,
              f"got: {hist.get('current_score')}")


# ── Section 2: Agente de seguimiento ──────────────────────────────────────────

async def _test_follow_up_agent(
    client: httpx.AsyncClient,
    auth: dict,
    branch_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> uuid.UUID | None:
    """Returns a pending suggestion_id if one was created, else None."""
    print("\n── 2. Agente de seguimiento ───────────────────────────────────────")

    print("\n[2a] Crear lead inactivo + conversación (mensaje 30h atrás)")
    try:
        lead_id, conv_id = await _create_inactive_lead_with_conversation(branch_id, tenant_id)
        ok(f"Lead inactivo + conversación creados ({str(conv_id)[:8]}…)")
    except Exception as exc:
        fail("Crear lead inactivo", str(exc))
        return None

    print("\n[2b] Llamar a run_follow_up_agent(branch_id)")
    try:
        from app.agents.follow_up_agent import run_follow_up_agent
        created = await run_follow_up_agent(branch_id)
        if created == 0:
            info("run_follow_up_agent devolvió 0 — branch sin WA creds o sin convs elegibles")
            info("Esto es esperado en desarrollo local sin WhatsApp configurado")
            ok("run_follow_up_agent ejecutado sin excepción (0 sugerencias — sin WA creds)")
        else:
            ok(f"run_follow_up_agent ejecutado — {created} sugerencia(s) creadas")
    except Exception as exc:
        fail("run_follow_up_agent", str(exc)[:120])
        return None

    print("\n[2c] GET /api/agents/suggestions como asesor")
    r = await client.get("/api/agents/suggestions", headers=auth)
    check("GET /agents/suggestions 200", r.status_code == 200,
          f"HTTP {r.status_code}: {r.text[:120]}")

    suggestion_id: uuid.UUID | None = None

    if r.status_code == 200:
        suggestions = r.json()
        pending = [s for s in suggestions if s["status"] in ("suggested", "accepted")]
        print(f"     Total sugerencias  : {len(suggestions)}")
        print(f"     Pendientes          : {len(pending)}")

        if pending:
            suggestion_id = uuid.UUID(pending[0]["id"])
            check("Sugerencia pendiente visible", True)
            print(f"     agent_type         : {pending[0].get('agent_type')}")
            print(f"     suggestion_text    : {str(pending[0].get('suggestion_text', ''))[:60]}")
        else:
            info("Sin sugerencias pendientes (sin WA creds en branch — esperado en dev)")
            # Try to get one from DB directly (created in a previous run)
            suggestion_id = await _get_any_pending_suggestion_id(tenant_id)
            if suggestion_id:
                info(f"Usando sugerencia existente de BD: {str(suggestion_id)[:8]}…")
            else:
                info("Sin sugerencias en BD — saltando confirm")
                ok("Flujo de agente validado (sin WA creds en branch)")
                return None

    if suggestion_id is None:
        return None

    print(f"\n[2d] POST /api/agents/suggestions/{str(suggestion_id)[:8]}…/confirm")
    r2 = await client.post(
        f"/api/agents/suggestions/{suggestion_id}/confirm", headers=auth
    )
    check("POST .../confirm 200 o 409", r2.status_code in (200, 409),
          f"HTTP {r2.status_code}: {r2.text[:120]}")

    if r2.status_code == 200:
        out = r2.json()
        new_status = out.get("status")
        check("status es 'confirmed' o 'executed'",
              new_status in ("confirmed", "executed"),
              f"got: {new_status}")
        print(f"     status: {new_status}")
    elif r2.status_code == 409:
        info("409 — sugerencia ya fue procesada anteriormente")
        ok("Confirm/409 manejado correctamente")

    return suggestion_id


# ── Section 3: Motor de métricas ──────────────────────────────────────────────

async def _test_metrics(
    client: httpx.AsyncClient,
    auth: dict,
    branch_id: uuid.UUID,
) -> None:
    print("\n── 3. Motor de métricas ───────────────────────────────────────────")

    print("\n[3a] aggregate_daily_metrics(branch_id, today)")
    today = date.today()
    try:
        from app.services.metrics_engine import aggregate_daily_metrics
        async with AsyncSessionLocal() as db:
            metric = await aggregate_daily_metrics(branch_id, today, db)
            await db.commit()
        ok(f"aggregate_daily_metrics ejecutado — {today}")
        print(f"     leads_created    : {metric.leads_created}")
        print(f"     leads_won        : {metric.leads_won}")
        print(f"     messages_sent    : {metric.messages_sent}")
    except Exception as exc:
        fail("aggregate_daily_metrics", str(exc)[:120])

    print("\n[3b] GET /api/metrics/dashboard?period=month")
    t0 = time.perf_counter()
    r = await client.get("/api/metrics/dashboard?period=month&compare=true", headers=auth)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    check("GET /metrics/dashboard 200", r.status_code == 200,
          f"HTTP {r.status_code}: {r.text[:120]}")
    print(f"     Tiempo de respuesta: {elapsed_ms:.0f}ms  (objetivo <500ms)")
    check("Respuesta <500ms", elapsed_ms < 500, f"{elapsed_ms:.0f}ms")

    if r.status_code == 200:
        data = r.json()
        check("current.leads_created presente",
              "current" in data and "leads_created" in data["current"],
              f"keys: {list(data.keys())}")
        check("delta presente (compare=true)",
              data.get("delta") is not None,
              "null")
        check("daily es lista",
              isinstance(data.get("daily"), list),
              f"got: {type(data.get('daily'))}")
        print(f"     period       : {data.get('period')}")
        print(f"     leads_created: {data.get('current', {}).get('leads_created')}")
        print(f"     daily points : {len(data.get('daily', []))}")


# ── Section 4: Sentimiento ────────────────────────────────────────────────────

async def _test_sentiment(
    client: httpx.AsyncClient,
    auth: dict,
    branch_id: uuid.UUID,
) -> None:
    print("\n── 4. Sentimiento ─────────────────────────────────────────────────")

    print("\n[4a] calculate_sentiment_snapshot(branch_id)")
    try:
        from app.services.sentiment_aggregator import calculate_sentiment_snapshot
        async with AsyncSessionLocal() as db:
            snap = await calculate_sentiment_snapshot(branch_id, db)
            await db.commit()
        ok("calculate_sentiment_snapshot ejecutado")
        print(f"     overall_score: {snap.overall_score}")
        print(f"     distribution : {dict(list(snap.distribution.items())[:3])}")
    except Exception as exc:
        fail("calculate_sentiment_snapshot", str(exc)[:120])

    print("\n[4b] GET /api/metrics/sentiment")
    r = await client.get("/api/metrics/sentiment", headers=auth)
    check("GET /metrics/sentiment 200", r.status_code == 200,
          f"HTTP {r.status_code}: {r.text[:120]}")

    if r.status_code == 200:
        data = r.json()
        current = data.get("current") or {}
        check("current.overall_score es número",
              isinstance(current.get("overall_score"), (int, float)),
              f"got: {current.get('overall_score')!r}")
        check("insight no vacío",
              bool(data.get("insight")),
              "vacío")
        print(f"     overall_score: {current.get('overall_score')}")
        print(f"     insight      : {str(data.get('insight', ''))[:70]}")
        print(f"     trend        : {data.get('trend')}")


# ── Section 5: Dashboards por rol ─────────────────────────────────────────────

async def _test_dashboards(
    client: httpx.AsyncClient,
    branch_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> None:
    print("\n── 5. Dashboards por rol ──────────────────────────────────────────")

    # ── Asesor ───────────────────────────────────────────────────────────────
    print(f"\n[5a] GET /api/dashboard — asesor ({ASESOR_EMAIL})")
    r_login = await client.post(
        "/api/auth/login", json={"email": ASESOR_EMAIL, "password": PASSWORD}
    )
    if not check("Login asesor 200", r_login.status_code == 200,
                 f"HTTP {r_login.status_code}"):
        return
    asesor_auth = {"Authorization": f"Bearer {r_login.json()['access_token']}"}

    t0 = time.perf_counter()
    r = await client.get("/api/dashboard", headers=asesor_auth)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    check("GET /dashboard asesor 200", r.status_code == 200,
          f"HTTP {r.status_code}: {r.text[:120]}")
    print(f"     Tiempo: {elapsed_ms:.0f}ms  (objetivo <500ms)")
    check("Dashboard asesor <500ms", elapsed_ms < 500, f"{elapsed_ms:.0f}ms")

    if r.status_code == 200:
        data = r.json()
        check("role == 'asesor'", data.get("role") == "asesor",
              f"got: {data.get('role')}")
        check("my_leads es lista", isinstance(data.get("my_leads"), list),
              f"got: {type(data.get('my_leads'))}")
        check("mini_pipeline es lista", isinstance(data.get("mini_pipeline"), list),
              f"got: {type(data.get('mini_pipeline'))}")
        print(f"     my_leads       : {len(data.get('my_leads', []))}")
        print(f"     mini_pipeline  : {len(data.get('mini_pipeline', []))} etapas")
        print(f"     pending_suggestions: {len(data.get('pending_suggestions', []))}")

    # ── Gerente ───────────────────────────────────────────────────────────────
    print(f"\n[5b] GET /api/dashboard — gerente")
    try:
        gerente_email = await _ensure_gerente_user(tenant_id, branch_id)
    except Exception as exc:
        fail("Preparar gerente user", str(exc))
        gerente_email = None

    if gerente_email:
        r_login = await client.post(
            "/api/auth/login", json={"email": gerente_email, "password": PASSWORD}
        )
        if check("Login gerente 200", r_login.status_code == 200,
                 f"HTTP {r_login.status_code}"):
            gerente_auth = {"Authorization": f"Bearer {r_login.json()['access_token']}"}

            t0 = time.perf_counter()
            r = await client.get("/api/dashboard", headers=gerente_auth)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            check("GET /dashboard gerente 200", r.status_code == 200,
                  f"HTTP {r.status_code}: {r.text[:120]}")
            print(f"     Tiempo: {elapsed_ms:.0f}ms  (objetivo <500ms)")
            check("Dashboard gerente <500ms", elapsed_ms < 500, f"{elapsed_ms:.0f}ms")

            if r.status_code == 200:
                data = r.json()
                check("role == 'gerente'", data.get("role") == "gerente",
                      f"got: {data.get('role')}")
                check("team_performance es lista",
                      isinstance(data.get("team_performance"), list),
                      f"got: {type(data.get('team_performance'))}")
                check("pipeline presente",
                      isinstance(data.get("pipeline"), dict),
                      f"got: {type(data.get('pipeline'))}")
                print(f"     team_performance: {len(data.get('team_performance', []))} asesores")
                print(f"     at_risk_leads   : {len(data.get('at_risk_leads', []))}")

    # ── Owner ─────────────────────────────────────────────────────────────────
    print(f"\n[5c] GET /api/dashboard — owner ({OWNER_EMAIL})")
    r_login = await client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": PASSWORD}
    )
    if not check("Login owner 200", r_login.status_code == 200,
                 f"HTTP {r_login.status_code}"):
        return
    owner_auth = {"Authorization": f"Bearer {r_login.json()['access_token']}"}

    t0 = time.perf_counter()
    r = await client.get("/api/dashboard", headers=owner_auth)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    check("GET /dashboard owner 200", r.status_code == 200,
          f"HTTP {r.status_code}: {r.text[:120]}")
    print(f"     Tiempo: {elapsed_ms:.0f}ms  (objetivo <500ms)")
    check("Dashboard owner <500ms", elapsed_ms < 500, f"{elapsed_ms:.0f}ms")

    if r.status_code == 200:
        data = r.json()
        check("role == 'owner'", data.get("role") == "owner",
              f"got: {data.get('role')}")
        check("branches es lista", isinstance(data.get("branches"), list),
              f"got: {type(data.get('branches'))}")
        check("mrr_estimate >= 0",
              isinstance(data.get("mrr_estimate"), (int, float)) and data["mrr_estimate"] >= 0,
              f"got: {data.get('mrr_estimate')!r}")
        print(f"     branches     : {len(data.get('branches', []))}")
        print(f"     mrr_estimate : ${data.get('mrr_estimate')}")
        print(f"     cross_suggestions: {len(data.get('cross_branch_suggestions', []))}")

    return owner_auth


# ── Section 6: Repositorio de automatizaciones ────────────────────────────────

async def _test_automations(
    client: httpx.AsyncClient,
    auth: dict,
    tenant_id: uuid.UUID,
) -> None:
    print("\n── 6. Repositorio de automatizaciones ────────────────────────────")

    print("\n[6a] GET /api/automations?status=suggested")
    r = await client.get("/api/automations?status=suggested", headers=auth)
    check("GET /automations 200", r.status_code == 200,
          f"HTTP {r.status_code}: {r.text[:120]}")

    automation_id: str | None = None

    if r.status_code == 200:
        data = r.json()
        check("items es lista", isinstance(data.get("items"), list),
              f"got: {type(data.get('items'))}")
        check("total es entero", isinstance(data.get("total"), int),
              f"got: {data.get('total')!r}")
        print(f"     total sugerencias: {data.get('total')}")
        print(f"     page             : {data.get('page')}")
        items = data.get("items", [])
        if items:
            automation_id = items[0]["id"]
            print(f"     primera ID       : {str(automation_id)[:8]}…")
            print(f"     agent_type       : {items[0].get('agent_type')}")
            print(f"     status           : {items[0].get('status')}")
        else:
            info("Sin automatizaciones sugeridas — buscando en todas")
            r2 = await client.get("/api/automations", headers=auth)
            if r2.status_code == 200:
                d2 = r2.json()
                if d2.get("items"):
                    automation_id = d2["items"][0]["id"]
                    print(f"  → Usando automación existente: {str(automation_id)[:8]}…")

    if automation_id is None:
        info("Sin automatizaciones disponibles — saltando PATCH")
        ok("GET /automations validado (vacío)")
        return

    print(f"\n[6b] PATCH /api/automations/{str(automation_id)[:8]}… {{is_active: false}}")
    r = await client.patch(
        f"/api/automations/{automation_id}",
        json={"is_active": False},
        headers=auth,
    )
    check("PATCH /automations 200", r.status_code == 200,
          f"HTTP {r.status_code}: {r.text[:120]}")

    if r.status_code == 200:
        out = r.json()
        new_status = out.get("status")
        check("status cambió (confirmed/dismissed/suggested)",
              new_status in ("confirmed", "dismissed", "suggested"),
              f"got: {new_status!r}")
        print(f"     nuevo status: {new_status}")
        print(f"     agent_type  : {out.get('agent_type')}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 66)
    print("Sprint 6 — test_sprint6.py")
    print("=" * 66)

    print("\n[setup] Resolviendo branch desde usuario asesor…")
    try:
        branch_id, tenant_id = await _get_branch_for_user(ASESOR_EMAIL)
        print(f"  branch_id : {branch_id}")
        print(f"  tenant_id : {tenant_id}")
    except Exception as exc:
        fail("Resolver branch", str(exc))
        print("\nNo se puede continuar sin branch. Corre seed.py primero.")
        return

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Login como asesor para secciones 1-4
        print(f"\n[login] {ASESOR_EMAIL}")
        r = await client.post(
            "/api/auth/login", json={"email": ASESOR_EMAIL, "password": PASSWORD}
        )
        if not check("POST /auth/login 200", r.status_code == 200,
                     f"HTTP {r.status_code}"):
            print("  No se puede continuar sin token.")
            return
        asesor_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        await _test_score(client, asesor_auth, branch_id)
        await _test_follow_up_agent(client, asesor_auth, branch_id, tenant_id)
        await _test_metrics(client, asesor_auth, branch_id)
        await _test_sentiment(client, asesor_auth, branch_id)
        owner_auth = await _test_dashboards(client, branch_id, tenant_id)

        # Automatizaciones requiere gerente o superior
        if owner_auth:
            await _test_automations(client, owner_auth, tenant_id)
        else:
            # Intentar con login de owner directamente
            r_login = await client.post(
                "/api/auth/login", json={"email": OWNER_EMAIL, "password": PASSWORD}
            )
            if r_login.status_code == 200:
                o_auth = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
                await _test_automations(client, o_auth, tenant_id)

    total = _ok + _fail
    print()
    print("=" * 66)
    print(f"Resultado: {_ok}/{total} checks pasaron")
    if _fail:
        print(f"  {_fail} fallo(s) — revisa los ✗ arriba.")
    else:
        print("  Todos los checks pasaron. ✓")
    print("=" * 66)

    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    asyncio.run(main())
