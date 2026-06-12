"""
Sprint 7 · P-08 — Agentes 5 y 6: lógica de detección

Agente 5 (profile_enrichment): detecta leads sin empresa con ≥3 mensajes,
  descarta confianza baja y evita duplicados en 72 h.

Agente 6 (reactivation): detecta leads inactivos 30+ días con al menos
  1 mensaje previo, evita duplicados en 7 días.

Anthropic se mockea con unittest.mock.AsyncMock — no se hacen llamadas reales.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.profile_enrichment_agent import run_profile_enrichment_agent
from app.agents.reactivation_agent import run_reactivation_agent
from app.models.agent import AgentSuggestion
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.models.lead import Lead, LeadStatus
from app.models.tenant import Branch, Tenant


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def tenant_a(db: AsyncSession, tenant: Tenant, branch: Branch) -> dict:
    """Dict con tenant_id y branch_id resueltos desde los fixtures de conftest."""
    return {"id": tenant.id, "branch_id": branch.id}


@pytest.fixture()
def mock_anthropic(monkeypatch):
    """
    Mockea _anthropic.messages.create en ambos agentes.
    Los tests asignan mock_anthropic.return_value al JSON string que devolvería Claude;
    el fixture lo envuelve en la estructura de respuesta correcta.
    """
    mock = AsyncMock()

    async def _side_effect(*args, **kwargs):
        item = MagicMock()
        item.text = mock.return_value
        resp = MagicMock()
        resp.content = [item]
        return resp

    mock.side_effect = _side_effect

    monkeypatch.setattr(
        "app.agents.profile_enrichment_agent._anthropic.messages.create", mock
    )
    monkeypatch.setattr(
        "app.agents.reactivation_agent._anthropic.messages.create", mock
    )
    return mock


# ── Helpers de datos ──────────────────────────────────────────────────────────


def _unique_phone() -> str:
    return f"+521{uuid.uuid4().int % 10_000_000_000:010d}"


async def _add_messages(db: AsyncSession, lead: Lead, count: int) -> None:
    if count == 0:
        return
    conv = Conversation(
        lead_id=lead.id,
        branch_id=lead.branch_id,
        status=ConversationStatus.ACTIVE,
        current_handler=ConversationHandler.BOT,
    )
    db.add(conv)
    await db.flush()
    for i in range(count):
        db.add(
            Message(
                conversation_id=conv.id,
                role=MessageRole.USER,
                content=f"Mensaje de prueba {i + 1}",
            )
        )
    await db.flush()


async def create_lead_without_company(
    db: AsyncSession, tenant_a: dict, *, message_count: int
) -> dict:
    lead = Lead(
        branch_id=tenant_a["branch_id"],
        tenant_id=tenant_a["id"],
        wa_phone=_unique_phone(),
        name="Sin Empresa",
        company=None,
        status=LeadStatus.NUEVO,
    )
    db.add(lead)
    await db.flush()
    await _add_messages(db, lead, message_count)
    return {"id": lead.id}


async def create_lead_with_company(
    db: AsyncSession, tenant_a: dict, *, company: str, message_count: int
) -> dict:
    lead = Lead(
        branch_id=tenant_a["branch_id"],
        tenant_id=tenant_a["id"],
        wa_phone=_unique_phone(),
        name="Con Empresa",
        company=company,
        status=LeadStatus.NUEVO,
    )
    db.add(lead)
    await db.flush()
    await _add_messages(db, lead, message_count)
    return {"id": lead.id}


async def create_inactive_lead(
    db: AsyncSession, tenant_a: dict, *, days_inactive: int, message_count: int
) -> dict:
    lead = Lead(
        branch_id=tenant_a["branch_id"],
        tenant_id=tenant_a["id"],
        wa_phone=_unique_phone(),
        name="Inactivo",
        company="Empresa Prueba SA",
        status=LeadStatus.NUEVO,
    )
    db.add(lead)
    await db.flush()

    past_ts = datetime.now(timezone.utc) - timedelta(days=days_inactive)
    await db.execute(
        update(Lead).where(Lead.id == lead.id).values(updated_at=past_ts)
    )
    await db.flush()
    await db.refresh(lead)

    await _add_messages(db, lead, message_count)
    return {"id": lead.id}


async def get_suggestions_for_lead(lead_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(AgentSuggestion).where(
                AgentSuggestion.action_payload["lead_id"].astext == str(lead_id)
            )
        )
    ).scalars().all()
    return [
        {
            "agent_type": s.agent_type,
            "suggestion_text": s.suggestion_text,
            "action_payload": s.action_payload,
        }
        for s in rows
    ]


# ── AGENTE 5 — ENRIQUECIMIENTO DE PERFIL ─────────────────────────────────────


async def test_agent5_triggers_on_no_company_with_messages(
    db: AsyncSession, tenant_a: dict, mock_anthropic
) -> None:
    """Agente 5 genera sugerencia para contacto sin empresa con ≥3 mensajes."""
    mock_anthropic.return_value = '{"company": "Empresas García SA", "confidence": "high"}'
    lead = await create_lead_without_company(db, tenant_a, message_count=3)
    await run_profile_enrichment_agent(tenant_a["id"], db)
    suggestions = await get_suggestions_for_lead(lead["id"], db)
    assert len(suggestions) == 1
    assert suggestions[0]["agent_type"] == "profile_enrichment"
    assert "Empresas García" in suggestions[0]["suggestion_text"]


async def test_agent5_skips_contact_with_company(
    db: AsyncSession, tenant_a: dict, mock_anthropic
) -> None:
    """Agente 5 NO actúa si el contacto ya tiene empresa."""
    lead = await create_lead_with_company(db, tenant_a, company="ACME", message_count=5)
    await run_profile_enrichment_agent(tenant_a["id"], db)
    suggestions = await get_suggestions_for_lead(lead["id"], db)
    assert len(suggestions) == 0


async def test_agent5_skips_contact_with_less_than_3_messages(
    db: AsyncSession, tenant_a: dict, mock_anthropic
) -> None:
    """Agente 5 NO actúa si hay menos de 3 mensajes."""
    lead = await create_lead_without_company(db, tenant_a, message_count=2)
    await run_profile_enrichment_agent(tenant_a["id"], db)
    suggestions = await get_suggestions_for_lead(lead["id"], db)
    assert len(suggestions) == 0


async def test_agent5_skips_low_confidence(
    db: AsyncSession, tenant_a: dict, mock_anthropic
) -> None:
    """Agente 5 NO crea sugerencia si confidence es 'low'."""
    mock_anthropic.return_value = '{"company": "Algo", "confidence": "low"}'
    lead = await create_lead_without_company(db, tenant_a, message_count=5)
    await run_profile_enrichment_agent(tenant_a["id"], db)
    suggestions = await get_suggestions_for_lead(lead["id"], db)
    assert len(suggestions) == 0


async def test_agent5_no_duplicate_within_72h(
    db: AsyncSession, tenant_a: dict, mock_anthropic
) -> None:
    """Agente 5 no crea sugerencia duplicada si ya existe una en las últimas 72 h."""
    mock_anthropic.return_value = '{"company": "ACME", "confidence": "high"}'
    lead = await create_lead_without_company(db, tenant_a, message_count=3)
    await run_profile_enrichment_agent(tenant_a["id"], db)
    await run_profile_enrichment_agent(tenant_a["id"], db)
    suggestions = await get_suggestions_for_lead(lead["id"], db)
    assert len(suggestions) == 1


# ── AGENTE 6 — REACTIVACIÓN ───────────────────────────────────────────────────


async def test_agent6_triggers_on_inactive_30_days(
    db: AsyncSession, tenant_a: dict, mock_anthropic
) -> None:
    """Agente 6 genera sugerencia para contacto sin actividad en 30+ días."""
    mock_anthropic.return_value = (
        '{"should_suggest": true, "message": "Hola, ¿seguimos en contacto?", "reason": "30 días inactivo"}'
    )
    lead = await create_inactive_lead(db, tenant_a, days_inactive=31, message_count=2)
    await run_reactivation_agent(tenant_a["id"], db)
    suggestions = await get_suggestions_for_lead(lead["id"], db)
    assert len(suggestions) == 1
    assert suggestions[0]["agent_type"] == "reactivation"
    assert "Hola" in suggestions[0]["suggestion_text"]


async def test_agent6_skips_contact_with_no_messages(
    db: AsyncSession, tenant_a: dict, mock_anthropic
) -> None:
    """Agente 6 NO actúa si el contacto nunca tuvo mensajes."""
    lead = await create_inactive_lead(db, tenant_a, days_inactive=35, message_count=0)
    await run_reactivation_agent(tenant_a["id"], db)
    suggestions = await get_suggestions_for_lead(lead["id"], db)
    assert len(suggestions) == 0


async def test_agent6_skips_active_contact(
    db: AsyncSession, tenant_a: dict, mock_anthropic
) -> None:
    """Agente 6 NO actúa si el contacto tuvo actividad en los últimos 30 días."""
    lead = await create_inactive_lead(db, tenant_a, days_inactive=5, message_count=3)
    await run_reactivation_agent(tenant_a["id"], db)
    suggestions = await get_suggestions_for_lead(lead["id"], db)
    assert len(suggestions) == 0


async def test_agent6_no_duplicate_within_7_days(
    db: AsyncSession, tenant_a: dict, mock_anthropic
) -> None:
    """Agente 6 no genera sugerencia si ya existe una de reactivación en los últimos 7 días."""
    mock_anthropic.return_value = (
        '{"should_suggest": true, "message": "test", "reason": "test"}'
    )
    lead = await create_inactive_lead(db, tenant_a, days_inactive=31, message_count=2)
    await run_reactivation_agent(tenant_a["id"], db)
    await run_reactivation_agent(tenant_a["id"], db)
    suggestions = await get_suggestions_for_lead(lead["id"], db)
    assert len(suggestions) == 1
