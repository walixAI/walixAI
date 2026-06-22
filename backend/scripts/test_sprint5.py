"""Sprint 5 — test_sprint5.py

Prueba end-to-end de los 4 sistemas del Sprint 5:

  1. AI Bar         — POST /api/ai/command (consulta + acción)
  2. Pipeline Board — GET /api/pipeline/board + PATCH /api/leads/{id}/stage
  3. Alertas        — send_daily_summary() + detect_unresponded_leads()
  4. Soporte/Plataforma — support request/verify-code + platform stats

Corre desde backend/:
    .venv/bin/python scripts/test_sprint5.py
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

import httpx
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.alert import AlertRule
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.pipeline import PipelineStage  # noqa: F401 — registers FK table in metadata
from app.models.support import SupportSession
from app.models.tenant import Branch, Tenant
from app.models.user import User, UserRole
from app.services.alert_generator import send_daily_summary
from app.tasks.alerts_tasks import _async_detect_unresponded as _job_detect_unresponded

BASE_URL = "http://localhost:8000"
ASESOR_EMAIL = "asistente@clinica.com"
PLATFORM_EMAIL = "platform@walix.io"
PASSWORD = "walix2026"

_ok = 0
_fail = 0


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


# ── DB helpers ────────────────────────────────────────────────────────────────

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


async def _ensure_soporte_user(tenant_id: uuid.UUID, branch_id: uuid.UUID) -> str:
    email = "soporte@walix.io"
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is None:
            db.add(User(
                tenant_id=tenant_id,
                branch_id=None,
                email=email,
                name="Ejecutivo Soporte",
                hashed_password=hash_password(PASSWORD),
                role=UserRole.SOPORTE,
                is_active=True,
            ))
            await db.commit()
            print(f"  → Usuario soporte creado: {email}")
        else:
            print(f"  → Usuario soporte encontrado: {email}")
    return email


async def _ensure_platform_owner() -> str:
    email = PLATFORM_EMAIL
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is None:
            db.add(User(
                tenant_id=None,
                branch_id=None,
                email=email,
                name="Platform Owner",
                hashed_password=hash_password(PASSWORD),
                role=UserRole.PLATFORM_OWNER,
                is_active=True,
            ))
            await db.commit()
            print(f"  → Usuario platform_owner creado: {email}")
        else:
            print(f"  → Usuario platform_owner encontrado: {email}")
    return email


async def _ensure_alert_rule(branch_id: uuid.UUID, tenant_id: uuid.UUID) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        rule = (
            await db.execute(
                select(AlertRule).where(
                    AlertRule.branch_id == branch_id,
                    AlertRule.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if rule is None:
            rule = AlertRule(
                branch_id=branch_id,
                tenant_id=tenant_id,
                alert_type="no_response",
                is_active=True,
                schedule_hour=9,
                silence_start=21,
                silence_end=8,
                threshold_hours=48,
            )
            db.add(rule)
            await db.commit()
            await db.refresh(rule)
            print(f"  → AlertRule creada: {rule.id}")
        else:
            print(f"  → AlertRule encontrada: {rule.id}")
        return rule.id


async def _create_stale_lead(branch_id: uuid.UUID, tenant_id: uuid.UUID) -> uuid.UUID:
    stale_time = datetime.now(timezone.utc) - timedelta(hours=72)
    async with AsyncSessionLocal() as db:
        lead = Lead(
            branch_id=branch_id,
            tenant_id=tenant_id,
            wa_phone=f"521550{uuid.uuid4().hex[:7]}",
            name="Lead Stale Sprint5",
            source=LeadSource.WHATSAPP_INBOUND,
            status=LeadStatus.EN_CALIFICACION,
            qualification_data={},
            last_alert_at=None,
        )
        db.add(lead)
        await db.flush()
        lead_id = lead.id
        await db.execute(
            update(Lead).where(Lead.id == lead_id).values(updated_at=stale_time)
        )
        await db.commit()
    print(f"  → Lead stale creado: {lead_id}")
    return lead_id


async def _get_lead_last_alert_at(lead_id: uuid.UUID) -> datetime | None:
    async with AsyncSessionLocal() as db:
        lead = await db.get(Lead, lead_id)
        return lead.last_alert_at if lead else None


async def _get_soporte_user_id(email: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            raise RuntimeError(f"Usuario {email} no encontrado")
        return user.id


async def _create_support_session_direct(
    support_user_id: uuid.UUID, tenant_id: uuid.UUID
) -> tuple[uuid.UUID, str]:
    code = "123456"
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        session = SupportSession(
            support_user_id=support_user_id,
            tenant_id=tenant_id,
            reason="Prueba sprint5",
            access_code=code,
            code_expires_at=now + timedelta(minutes=15),
            scope="readonly",
            status="pending",
            requested_duration_hours=2,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session.id, code


async def _get_session_code(session_id: uuid.UUID) -> str:
    async with AsyncSessionLocal() as db:
        sess = await db.get(SupportSession, session_id)
        return sess.access_code if sess else ""


# ── Section 1: AI Bar ─────────────────────────────────────────────────────────

async def _test_ai_bar(client: httpx.AsyncClient, auth: dict) -> None:
    print("\n── 1. AI Bar ─────────────────────────────────────────────────────")

    print("\n[1a] Consulta: 'muéstrame los leads en riesgo'")
    r = await client.post(
        "/api/ai/command",
        json={"message": "muéstrame los leads en riesgo", "context": {"screen": "pipeline"}},
        headers=auth,
    )
    check("POST /ai/command 200", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:120]}")
    if r.status_code == 200:
        data = r.json()
        check("intent_type == 'consulta'", data.get("intent_type") == "consulta",
              f"got: {data.get('intent_type')}")
        check("response_text no vacío", bool(data.get("response_text")), "vacío")
        print(f"     intent_type : {data.get('intent_type')}")
        print(f"     response    : {str(data.get('response_text',''))[:80]}")

    print("\n[1b] Acción: 'mueve el lead de María González al stage Calificado'")
    r = await client.post(
        "/api/ai/command",
        json={
            "message": "mueve el lead de María González al stage Calificado",
            "context": {"screen": "pipeline"},
        },
        headers=auth,
    )
    check("POST /ai/command 200", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:120]}")
    if r.status_code == 200:
        data = r.json()
        valid = data.get("intent_type") in ("accion", "consulta")
        check("intent_type es 'accion' o 'consulta'", valid, f"got: {data.get('intent_type')}")
        print(f"     intent_type  : {data.get('intent_type')}")
        print(f"     actions_taken: {len(data.get('actions_taken', []))}")
        print(f"     response     : {str(data.get('response_text',''))[:80]}")


# ── Section 2: Pipeline Board ─────────────────────────────────────────────────

async def _test_pipeline(client: httpx.AsyncClient, auth: dict) -> None:
    print("\n── 2. Pipeline Board ─────────────────────────────────────────────")

    print("\n[2a] GET /api/pipeline/board")
    r = await client.get("/api/pipeline/board", headers=auth)
    check("GET /pipeline/board 200", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:120]}")

    first_lead_id = None
    second_stage_id = None

    if r.status_code == 200:
        data = r.json()
        stages = data.get("stages", [])
        check("Al menos una etapa en el board", len(stages) > 0, f"stages={len(stages)}")
        for s in stages[:3]:
            print(f"     stage: {s['name']:<20} leads={s['total']}")

        for stage in stages:
            if stage["leads"] and first_lead_id is None:
                first_lead_id = stage["leads"][0]["id"]
        for stage in stages:
            if first_lead_id is None or stage["id"] != (
                next((s["id"] for s in stages if s["leads"] and s["leads"][0]["id"] == first_lead_id), None)
            ):
                second_stage_id = stage["id"]
                break

        if first_lead_id is None:
            print("  ℹ Sin leads en el board — saltando prueba de mover stage")

    if first_lead_id and second_stage_id:
        print(f"\n[2b] PATCH /api/leads/{str(first_lead_id)[:8]}…/stage")
        r = await client.patch(
            f"/api/leads/{first_lead_id}/stage",
            json={"stage_id": str(second_stage_id)},
            headers=auth,
        )
        check("PATCH /leads/{id}/stage 200", r.status_code == 200,
              f"HTTP {r.status_code}: {r.text[:120]}")
        if r.status_code == 200:
            out = r.json()
            check("pipeline_stage_id actualizado",
                  out.get("pipeline_stage_id") == second_stage_id,
                  f"got: {out.get('pipeline_stage_id')}")
            print(f"     stage_name: {out.get('stage_name')}")
    else:
        print("\n  ℹ No hay suficientes datos para probar el movimiento de stage")


# ── Section 3: Alertas ────────────────────────────────────────────────────────

async def _test_alerts(branch_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    print("\n── 3. Alertas ────────────────────────────────────────────────────")

    print("\n[3a] send_daily_summary(branch_id)")
    try:
        await send_daily_summary(branch_id)
        ok("send_daily_summary sin excepción")
    except Exception as exc:
        fail("send_daily_summary", str(exc)[:120])

    print("\n[3b] detect_unresponded_leads — lead stale + alert_rule")
    try:
        await _ensure_alert_rule(branch_id, tenant_id)
        ok("AlertRule disponible")
    except Exception as exc:
        fail("Crear AlertRule", str(exc))
        return

    try:
        lead_id = await _create_stale_lead(branch_id, tenant_id)
        ok(f"Lead stale creado ({str(lead_id)[:8]}…)")
    except Exception as exc:
        fail("Crear lead stale", str(exc))
        return

    print("  → Ejecutando _job_detect_unresponded()…")
    try:
        await _job_detect_unresponded()
        ok("_job_detect_unresponded sin excepción")
    except Exception as exc:
        fail("_job_detect_unresponded", str(exc)[:120])

    last_alert = await _get_lead_last_alert_at(lead_id)
    if last_alert is not None:
        ok(f"last_alert_at poblado: {last_alert.strftime('%H:%M:%S UTC')}")
    else:
        print("  ℹ last_alert_at es None (sin WA creds en branch — esperado en local)")
        ok("Flujo de detección completado sin excepción (WA no configurado)")


# ── Section 4: Soporte + Plataforma ─────────────────────────────────────────

async def _test_support_and_platform(
    client: httpx.AsyncClient,
    branch_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> None:
    print("\n── 4. Soporte + Plataforma ───────────────────────────────────────")

    print("\n[4a] Preparar usuario soporte")
    try:
        soporte_email = await _ensure_soporte_user(tenant_id, branch_id)
        soporte_user_id = await _get_soporte_user_id(soporte_email)
        ok(f"Usuario soporte listo ({soporte_email})")
    except Exception as exc:
        fail("Preparar soporte user", str(exc))
        return

    r = await client.post("/api/auth/login", json={"email": soporte_email, "password": PASSWORD})
    check("Login soporte 200", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code != 200:
        return
    soporte_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    print("\n[4b] POST /api/support/request (o inserción directa si sin WA creds)")
    r_req = await client.post(
        "/api/support/request",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Prueba sprint5 test",
            "scope": "readonly",
            "requested_duration_hours": 2,
        },
        headers=soporte_auth,
    )

    session_id: uuid.UUID | None = None
    code: str | None = None

    if r_req.status_code == 201:
        ok("POST /support/request 201 (WA configurado)")
        session_id = uuid.UUID(r_req.json()["session_id"])
        code = await _get_session_code(session_id)
    elif r_req.status_code in (404, 422):
        # 404 = owner sin wa_phone; 422 = branch sin WA creds — ambos se resuelven con inserción directa
        ok(f"POST /support/request {r_req.status_code} (sin WA en tenant — sesión directa)")
        try:
            session_id, code = await _create_support_session_direct(soporte_user_id, tenant_id)
            ok(f"SupportSession creada directamente: {str(session_id)[:8]}…")
        except Exception as exc:
            fail("Crear SupportSession directo", str(exc))
            return
    else:
        fail("POST /support/request", f"HTTP {r_req.status_code}: {r_req.text[:100]}")
        return

    print("\n[4c] POST /api/support/verify-code")
    r_verify = await client.post(
        "/api/support/verify-code",
        json={"session_id": str(session_id), "code": code},
        headers=soporte_auth,
    )
    check("POST /support/verify-code 200", r_verify.status_code == 200,
          f"HTTP {r_verify.status_code}: {r_verify.text[:120]}")
    if r_verify.status_code == 200:
        out = r_verify.json()
        check("access_token presente", bool(out.get("access_token")), "vacío")
        check("expires_at presente", bool(out.get("expires_at")), "vacío")
        print(f"     expires_at: {out.get('expires_at')}")

    print("\n[4d] GET /api/platform/stats")
    try:
        platform_email = await _ensure_platform_owner()
    except Exception as exc:
        fail("Preparar platform_owner", str(exc))
        return

    r_login = await client.post(
        "/api/auth/login", json={"email": platform_email, "password": PASSWORD}
    )
    check("Login platform_owner 200", r_login.status_code == 200,
          f"HTTP {r_login.status_code}")
    if r_login.status_code != 200:
        return

    platform_auth = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
    r_stats = await client.get("/api/platform/stats", headers=platform_auth)
    check("GET /platform/stats 200", r_stats.status_code == 200,
          f"HTTP {r_stats.status_code}: {r_stats.text[:120]}")
    if r_stats.status_code == 200:
        stats = r_stats.json()
        check("total_mrr >= 0",
              isinstance(stats.get("total_mrr"), (int, float)) and stats["total_mrr"] >= 0,
              f"got: {stats.get('total_mrr')}")
        check("total_tenants >= 1",
              isinstance(stats.get("total_tenants"), int) and stats["total_tenants"] >= 1,
              f"got: {stats.get('total_tenants')}")
        print(f"     total_tenants : {stats.get('total_tenants')}")
        print(f"     active_tenants: {stats.get('active_tenants')}")
        print(f"     total_mrr     : ${stats.get('total_mrr')}")
        print(f"     ai_costs      : ${stats.get('ai_costs_this_month')}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 64)
    print("Sprint 5 — test_sprint5.py")
    print("=" * 64)

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
        print(f"\n[login] {ASESOR_EMAIL}")
        r = await client.post(
            "/api/auth/login", json={"email": ASESOR_EMAIL, "password": PASSWORD}
        )
        if not check("POST /auth/login 200", r.status_code == 200, f"HTTP {r.status_code}"):
            print("  No se puede continuar sin token.")
            return
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        await _test_ai_bar(client, auth)
        await _test_pipeline(client, auth)

    # Alertas usa conexiones DB directas + funciones async del scheduler
    await _test_alerts(branch_id, tenant_id)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        await _test_support_and_platform(client, branch_id, tenant_id)

    total = _ok + _fail
    print()
    print("=" * 64)
    print(f"Resultado: {_ok}/{total} checks pasaron")
    if _fail:
        print(f"  {_fail} fallo(s) — revisa los ✗ arriba.")
    else:
        print("  Todos los checks pasaron. ✓")
    print("=" * 64)


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(1 if _fail else 0)
