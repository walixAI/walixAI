"""
Regresión — Lookups pre-tenant seguros (login, check-email, webhook de WhatsApp).

Código auditado:
  - alembic/versions/l7m8n9o0p1q2_pretenant_lookup_functions.py — funciones
    SECURITY DEFINER fn_lookup_tenant_by_email / fn_lookup_tenant_by_wa_phone_id.
    Devuelven SOLO tenant_id; REVOKE ALL FROM PUBLIC + GRANT EXECUTE a
    walix_app únicamente.
  - app/api/auth.py — login/register/check-email/register_v2 resuelven el
    tenant vía _resolve_tenant_by_email() (que llama la función) ANTES de
    cualquier SELECT completo — un SELECT directo sin tenant conocido nunca
    vería filas bajo RLS con un rol sin BYPASSRLS.
  - app/api/webhooks.py — receive_whatsapp_webhook hace lo mismo para
    Branch por wa_phone_number_id.
  - app/core/database.py — set_tenant_context(), el helper que hace
    set_config() mid-request una vez resuelto el tenant por esas funciones.

Estos tests impersonan walix_app vía SET LOCAL ROLE dentro de la conexión
admin de la suite (ver impersonate_walix_app_or_skip en conftest.py, y el
docstring de test_multi_tenancy.py — "Cómo se prueba RLS de verdad" — para
el porqué de este mecanismo en vez de repuntar el DATABASE_URL de toda la
suite de tests).

FUERA DE ALCANCE de este módulo (documentado, no fallado silenciosamente):
  - El endpoint HTTP completo del webhook (firma HMAC, dedup por Redis,
    BackgroundTasks, pipeline del bot) — eso lo cubre
    backend/scripts/test_webhook.py contra un servidor real. Acá solo se
    prueba el MECANISMO de resolución de tenant que ahora usa ese endpoint.
  - app/ai/bot_engine.py:process_message (llamado como BackgroundTask desde
    el webhook, ya con tenant_id conocido) sigue usando AsyncSessionLocal()
    sin set_tenant_context — es uno de los ~24 call-sites explícitamente
    fuera de alcance de este prompt (Parte 2). El mensaje entrante SÍ
    resuelve la Branch correctamente ahora; la respuesta del bot en sí
    todavía requeriría el rol admin (bypass) hasta que se aborde ese
    call-site puntual.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_tenant_context
from app.models.lead import Lead, LeadStatus
from app.models.tenant import Branch
from app.models.user import User
from tests.regression.conftest import impersonate_walix_app_or_skip


# ── Login / check-email bajo RLS real ─────────────────────────────────────────

async def test_login_succeeds_under_real_rls_via_pretenant_lookup(
    client: AsyncClient, db: AsyncSession, owner_user: User, tenant,
) -> None:
    """Antes de este fix, bajo walix_app, login devolvía 401 SIEMPRE —
    incluso con credenciales correctas — porque `SELECT users WHERE email`
    corre sin tenant conocido y RLS bloquea la query por completo. Ver
    hallazgo documentado en la sesión que generó este módulo."""
    await impersonate_walix_app_or_skip(db)

    r = await client.post(
        "/api/auth/login",
        json={"email": owner_user.email, "password": "test1234"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["id"] == str(owner_user.id)
    assert body["user"]["tenant_id"] == str(tenant.id)


async def test_login_unknown_email_returns_generic_401_no_leak(
    client: AsyncClient, db: AsyncSession,
) -> None:
    """fn_lookup_tenant_by_email devuelve NULL para un email que no existe en
    NINGÚN tenant — el mensaje de error debe seguir siendo genérico, igual
    que antes del fix, para no revelar si el email existe o no."""
    await impersonate_walix_app_or_skip(db)

    r = await client.post(
        "/api/auth/login",
        json={"email": "no-existe-jamas@nowhere.test", "password": "cualquiera"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"


async def test_check_email_reports_taken_and_available_under_rls(
    client: AsyncClient, db: AsyncSession, owner_user: User,
) -> None:
    await impersonate_walix_app_or_skip(db)

    taken = await client.post("/api/auth/check-email", json={"email": owner_user.email})
    assert taken.status_code == 200, taken.text
    assert taken.json() == {"available": False}

    free = await client.post(
        "/api/auth/check-email", json={"email": "nadie-usa-este-email@nowhere.test"}
    )
    assert free.status_code == 200
    assert free.json() == {"available": True}


# ── Permisos de las funciones SECURITY DEFINER ────────────────────────────────

async def test_pretenant_functions_have_no_public_grant(db: AsyncSession) -> None:
    """REVOKE ALL ... FROM PUBLIC en l7m8n9o0p1q2 — confirma contra el
    catálogo real de permisos que ningún rol sin GRANT EXECUTE explícito
    puede invocar estas funciones, y que walix_app sí lo tiene."""
    rows = (
        await db.execute(
            text(
                "SELECT routine_name, grantee FROM information_schema.routine_privileges "
                "WHERE routine_name IN "
                "('fn_lookup_tenant_by_email', 'fn_lookup_tenant_by_wa_phone_id')"
            )
        )
    ).fetchall()
    grantees = {(row[0], row[1]) for row in rows}

    assert not any(grantee == "PUBLIC" for _name, grantee in grantees), (
        f"PUBLIC no debería tener EXECUTE sobre estas funciones — grants actuales: {grantees}"
    )
    assert ("fn_lookup_tenant_by_email", "walix_app") in grantees
    assert ("fn_lookup_tenant_by_wa_phone_id", "walix_app") in grantees


# ── Webhook: mecanismo de resolución de Branch ────────────────────────────────

async def test_webhook_branch_lookup_resolves_under_rls_via_pretenant_function(
    db: AsyncSession, tenant, branch: Branch,
) -> None:
    """Mismo mecanismo que ahora usa receive_whatsapp_webhook en
    app/api/webhooks.py: fn_lookup_tenant_by_wa_phone_id + set_tenant_context
    antes del SELECT completo de la Branch. No dispara el endpoint HTTP
    completo (ver docstring del módulo) — prueba específicamente que la
    resolución de tenant ya no queda bloqueada por RLS."""
    branch.wa_phone_number_id = "PRETENANT_TEST_PHONE_ID"
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    tenant_id = (
        await db.execute(
            text("SELECT fn_lookup_tenant_by_wa_phone_id(:pid)"),
            {"pid": "PRETENANT_TEST_PHONE_ID"},
        )
    ).scalar_one_or_none()
    assert tenant_id == tenant.id

    await set_tenant_context(db, tenant_id)
    resolved = (
        await db.execute(
            select(Branch).where(Branch.wa_phone_number_id == "PRETENANT_TEST_PHONE_ID")
        )
    ).scalar_one_or_none()
    assert resolved is not None
    assert resolved.id == branch.id


async def test_webhook_lookup_returns_none_for_unknown_phone_id(db: AsyncSession) -> None:
    await impersonate_walix_app_or_skip(db)

    tenant_id = (
        await db.execute(
            text("SELECT fn_lookup_tenant_by_wa_phone_id(:pid)"),
            {"pid": "NUMERO_QUE_NO_EXISTE_JAMAS"},
        )
    ).scalar_one_or_none()
    assert tenant_id is None


# ── Cross-tenant: el contexto resuelto dinámicamente no filtra de más ────────

async def test_login_resolved_context_does_not_leak_other_tenant_data(
    client: AsyncClient, db: AsyncSession, owner_user: User, tenant, other_tenant_ctx: dict,
) -> None:
    """El tenant se resuelve dinámicamente (vía la función) en vez de venir
    ya fijo en un set_config() explícito como en el resto de la suite —
    confirma que el contexto resultante sigue exactamente igual de
    restringido: la función no se convirtió en una puerta trasera para ver
    más de lo que debería."""
    # Lead de OTRO tenant, insertado como admin (todavía sin impersonar)
    # ANTES de resolver ningún contexto — así no colisiona con la policy de
    # INSERT una vez que la sesión quede fijada al tenant A.
    other_lead_id = uuid.uuid4()
    other_lead = Lead(
        id=other_lead_id,
        branch_id=other_tenant_ctx["branch"].id,
        tenant_id=other_tenant_ctx["tenant"].id,
        wa_phone="+5215500000097",
        name="Lead Tenant B (pretenant test)",
        status=LeadStatus.NUEVO,
    )
    db.add(other_lead)
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    r = await client.post(
        "/api/auth/login",
        json={"email": owner_user.email, "password": "test1234"},
    )
    assert r.status_code == 200, r.text

    # Login dejó app.current_tenant_id fijado al tenant A (el de owner_user) —
    # una query RAW sin WHERE tenant_id sobre el lead del tenant B no debe
    # devolver nada, igual que en test_multi_tenancy.py.
    leaked = (
        await db.execute(text("SELECT id FROM leads WHERE id = :lid"), {"lid": str(other_lead_id)})
    ).scalar_one_or_none()
    assert leaked is None
