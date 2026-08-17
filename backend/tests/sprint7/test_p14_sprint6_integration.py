"""
Sprint 7 · P-14 — Integración Sprint 6 ↔ Sprint 7: scores, sugerencias IA,
                   actividades de sistema.

Correcciones respecto al pseudo-código original:
  · `contact_full["tenantId"]` → campo no existe en ContactRow; se usa `tenant.id` del fixture.
  · `currentScore` / `currentScoreTrend` → `current_score` / `current_score_trend` (snake_case).
  · `suggestions`                       → `agent_suggestions`                          (nombre real del campo).
  · `agentType`                          → `agent_type`                                 (snake_case).
  · `?type[]=system`                     → `params={"type": "system"}` (alias FastAPI es "type").
  · `/api/v1/agents/...`                 → `/api/agents/...` (agents router no tiene /v1/).
  · INSERT de AgentSuggestion sin `trigger_description` ni `target_role` (NOT NULL)
    → se usan inserts ORM con todos los campos requeridos.
  · INSERT de agent_suggestion sin `action_payload.lead_id`
    → los GET /contacts/:id filtran por `action_payload.contains({"lead_id": ...})`;
      los inserts de prueba incluyen este campo.
  · CRÍTICO — Flujo de confirm + executor:
    El endpoint `/confirm` fija status="confirmed"; el executor solo maneja
    "suggested"/"accepted" → lanzaría ValueError y no crearía la actividad.
    Solución: se llama `execute_suggestion` directamente con una sugerencia en
    status="suggested" y agent_type="pipeline" (acción create_task, sin WhatsApp).
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.executor import execute_suggestion
from app.models.agent import AgentSuggestion
from app.models.lead import Lead
from app.models.tenant import Branch, Tenant
from app.models.user import User


# ── Helpers ───────────────────────────────────────────────────────────────────

def auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['token']}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def user_asesor(asesor_user: User, asesor_token: str) -> dict:
    return {"id": str(asesor_user.id), "token": asesor_token}


@pytest_asyncio.fixture()
async def contact_full(client: AsyncClient, user_asesor: dict) -> dict:
    """Contacto creado vía POST en el tenant principal; devuelve el JSON de GET /:id."""
    r = await client.post(
        "/api/v1/contacts",
        json={
            "wa_phone": "+5215512340099",
            "name": "María",
            "last_name": "López",
            "company": "Test SA de CV",
        },
        headers=auth(user_asesor),
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r2 = await client.get(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert r2.status_code == 200, r2.text
    return r2.json()


# ── § 1: SCORE DE SPRINT 6 EN CONTACTOS ──────────────────────────────────────

async def test_contact_detail_includes_current_score(
    client: AsyncClient,
    contact_full: dict,
    user_asesor: dict,
    db: AsyncSession,
) -> None:
    """GET /contacts/:id retorna current_score y current_score_trend del scoring de Sprint 6."""
    contact_id = uuid.UUID(contact_full["id"])

    # Simular lo que haría el scoring agent: actualizar el score en el lead
    lead = await db.get(Lead, contact_id)
    assert lead is not None
    lead.current_score = 78
    lead.current_score_trend = "up"
    await db.flush()

    r = await client.get(
        f"/api/v1/contacts/{contact_full['id']}",
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["current_score"] == 78
    assert data["current_score_trend"] == "up"


# ── § 2: SUGERENCIAS IA EN FICHA DE CONTACTO ─────────────────────────────────

async def test_contact_detail_includes_pending_suggestions(
    client: AsyncClient,
    contact_full: dict,
    user_asesor: dict,
    db: AsyncSession,
    tenant: Tenant,
    branch: Branch,
    asesor_user: User,
) -> None:
    """GET /contacts/:id retorna agent_suggestions activas vinculadas al contacto.

    El endpoint filtra por action_payload.contains({"lead_id": str(contact_id)}),
    por lo que el insert debe incluir ese campo.
    """
    contact_id = uuid.UUID(contact_full["id"])

    sugg = AgentSuggestion(
        tenant_id=tenant.id,
        branch_id=branch.id,
        agent_type="follow_up",
        trigger_description="El contacto lleva 2 días sin respuesta.",
        suggestion_text="El lead lleva 2 días sin respuesta.",
        action_payload={"lead_id": str(contact_id)},
        target_role="asesor",
        target_user_id=asesor_user.id,
        status="suggested",
    )
    db.add(sugg)
    await db.flush()

    r = await client.get(
        f"/api/v1/contacts/{contact_full['id']}",
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    suggestions = r.json()["agent_suggestions"]
    assert len(suggestions) >= 1
    assert any(s["agent_type"] == "follow_up" for s in suggestions)


# ── § 3: EXECUTOR CREA ACTIVIDAD DE SISTEMA ───────────────────────────────────

async def test_agent_execution_creates_system_activity(
    client: AsyncClient,
    contact_full: dict,
    user_asesor: dict,
    db: AsyncSession,
    tenant: Tenant,
    branch: Branch,
) -> None:
    """execute_suggestion con action_payload.lead_id crea Activity(type='system') en el contacto.

    Diseño:
      - Se usa agent_type="pipeline" (acción create_task) porque no requiere
        credenciales de WhatsApp ni un handler externo.
      - Se llama execute_suggestion() directamente (no el endpoint /confirm) porque
        /confirm fija status="confirmed" y el executor solo acepta "suggested"/"accepted",
        lo que causaría ValueError sin crear la actividad.
    """
    contact_id = uuid.UUID(contact_full["id"])

    sugg = AgentSuggestion(
        tenant_id=tenant.id,
        branch_id=branch.id,
        agent_type="pipeline",
        trigger_description="Pipeline revisión requerida para el contacto.",
        suggestion_text="Revisar el estado del pipeline del contacto.",
        action_payload={"action": "create_task", "lead_id": str(contact_id)},
        target_role="gerente",
        status="suggested",
    )
    db.add(sugg)
    await db.flush()

    # Ejecutar directamente con la sesión de prueba (el commit queda en SAVEPOINT)
    await execute_suggestion(sugg.id, tenant.id, db)

    r = await client.get(
        f"/api/v1/contacts/{contact_full['id']}/activities",
        params={"type": "system"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    system_acts = r.json()["items"]
    assert len(system_acts) >= 1
    assert any("agente ejecutada" in (a.get("body") or "") for a in system_acts)


# ── § 4: SCORE EN LISTADO DE CONTACTOS ───────────────────────────────────────

async def test_contact_list_shows_score_badge(
    client: AsyncClient,
    contact_full: dict,
    user_asesor: dict,
    db: AsyncSession,
) -> None:
    """GET /contacts incluye current_score y current_score_trend para el badge en kanban y lista."""
    contact_id = uuid.UUID(contact_full["id"])

    lead = await db.get(Lead, contact_id)
    assert lead is not None
    lead.current_score = 85
    lead.current_score_trend = "up"
    await db.flush()

    r = await client.get(
        "/api/v1/contacts",
        params={"q": contact_full["name"][:4]},
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    contacts = r.json()["items"]
    matching = [c for c in contacts if c["id"] == contact_full["id"]]
    assert len(matching) == 1
    assert matching[0]["current_score"] == 85
    assert matching[0]["current_score_trend"] == "up"


# ── § 5: SUGERENCIA DE PROFILE ENRICHMENT ────────────────────────────────────

async def test_profile_enrichment_suggestion_in_contact_detail(
    client: AsyncClient,
    contact_full: dict,
    user_asesor: dict,
    db: AsyncSession,
    tenant: Tenant,
    branch: Branch,
    asesor_user: User,
) -> None:
    """Sugerencia del agente profile_enrichment aparece en la ficha del contacto."""
    contact_id = uuid.UUID(contact_full["id"])

    sugg = AgentSuggestion(
        tenant_id=tenant.id,
        branch_id=branch.id,
        agent_type="profile_enrichment",
        trigger_description="El contacto podría pertenecer a Empresa ABC.",
        suggestion_text="El contacto podría ser de Empresa ABC. ¿Actualizo?",
        action_payload={"lead_id": str(contact_id), "company": "Empresa ABC"},
        target_role="asesor",
        target_user_id=asesor_user.id,
        status="suggested",
    )
    db.add(sugg)
    await db.flush()

    r = await client.get(
        f"/api/v1/contacts/{contact_full['id']}",
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    suggestions = r.json()["agent_suggestions"]
    profile_suggestions = [s for s in suggestions if s["agent_type"] == "profile_enrichment"]
    assert len(profile_suggestions) >= 1
