"""Celery task: update AI entity context after a memory event (Etapa 6.2).

Pattern mirrors agent_tasks.py: asyncio.run() via run_async(), NullPool session,
max_retries with backoff.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.celery_app import celery_app
from app.core import database as _database
from app.core.config import settings
from app.core.database import set_tenant_context
from app.models.agent import AgentSuggestion
from app.models.ai_memory import AIEntityContext, AIMemoryEvent
from app.tasks._helpers import run_async

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# ── Prompts ────────────────────────────────────────────────────────────────────

_SYSTEM = (
    "Eres el motor de memoria de IA del CRM Walix. "
    "Analizas eventos de negocio y actualizas el contexto de una entidad. "
    "Responde EXCLUSIVAMENTE con JSON válido, sin markdown ni explicaciones."
)

_USER_TMPL = """\
Entidad: {entity_type} / {entity_id}

Contexto previo:
{prev_context}

Últimos {n} eventos (más reciente primero):
{events_json}

Devuelve un objeto JSON con exactamente estos campos:
{{
  "context_summary": "<resumen factual en español, máx 600 caracteres>",
  "key_facts": ["<hecho 1>", ..., "<hecho 5-8>"],
  "sentiment": "<positive|neutral|negative|unknown>",
  "urgency_score": <entero 0-100>,
  "proactive_suggestion": null
}}

Si urgency_score > 70, reemplaza null por:
{{
  "text": "<sugerencia breve>",
  "action_type": "<tipo>",
  "action_payload": {{}},
  "priority": "<high|medium|low>"
}}
"""

# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("No JSON in LLM response")
    return json.loads(match.group())


def _upsert_stmt(values: dict[str, Any]) -> Any:
    """Build a PostgreSQL INSERT … ON CONFLICT DO UPDATE statement."""
    return (
        pg_insert(AIEntityContext)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_ai_entity_context_tenant_type_entity",
            set_={k: values[k] for k in (
                "context_summary", "key_facts", "sentiment",
                "urgency_score", "last_interaction", "updated_at",
            ) if k in values},
        )
    )


async def _create_agent_suggestion(
    db,
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    urgency: int,
    proactive: dict[str, Any],
) -> None:
    from app.models.deal import Deal
    from app.models.lead import Lead
    from app.models.user import User

    suggestion_text = str(proactive.get("text", ""))[:120]
    if not suggestion_text:
        return

    target_user_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None

    if entity_type == "deal":
        deal = await db.get(Deal, entity_id)
        if deal:
            target_user_id = deal.owner_id
            lead = await db.get(Lead, deal.lead_id) if deal.lead_id else None
            if lead:
                branch_id = lead.branch_id

    if target_user_id is None:
        row = (await db.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.role == "owner",
                User.is_active.is_(True),
            ).limit(1)
        )).scalar_one_or_none()
        if row:
            target_user_id = row.id
            branch_id = row.branch_id

    db.add(AgentSuggestion(
        tenant_id=tenant_id,
        branch_id=branch_id,
        agent_type="pipeline",
        trigger_description=f"Urgency {urgency}/100 — {entity_type}/{entity_id}",
        suggestion_text=suggestion_text,
        action_payload={
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action_type": proactive.get("action_type"),
            "payload": proactive.get("action_payload", {}),
            "priority": proactive.get("priority", "medium"),
        },
        target_role="owner",
        target_user_id=target_user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    ))


# ── Task ───────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="app.tasks.ai_memory_tasks.update_entity_context_task",
    max_retries=3,
    default_retry_delay=60,
)
def update_entity_context_task(self, memory_event_id: str) -> dict:
    """Recalculate AIEntityContext using Claude Haiku after a memory event."""

    async def _run() -> dict:
        # _database.AsyncSessionLocal (no un import directo) — el import
        # directo se resuelve al importar el módulo, ANTES de que
        # worker_process_init (celery_app.py) reemplace la sessionmaker por
        # la versión NullPool del worker; con el atributo del módulo, cada
        # llamada relee el valor actual. Ver hallazgo del 2026-08-17.
        async with _database.AsyncSessionLocal() as db:
            # 1. Resolve tenant_id via SECURITY DEFINER lookup — ai_memory_events
            # tiene RLS desde la migración p1q2r3s4t5u6, así que un db.get()
            # directo no vería la fila sin tenant context, y todavía no lo
            # conocemos (es justo lo que estamos por descubrir). Ver
            # fn_lookup_ai_memory_event_tenant.
            event_id = uuid.UUID(memory_event_id)
            tenant_id = (await db.execute(
                text("SELECT fn_lookup_ai_memory_event_tenant(:id)"), {"id": event_id}
            )).scalar_one_or_none()
            if tenant_id is None:
                logger.warning("[ai_memory] event %s not found — skip", memory_event_id)
                return {"status": "skipped", "reason": "event_not_found"}

            await set_tenant_context(db, tenant_id)

            # Ahora sí, bajo el tenant correcto — agent_suggestions y users
            # también tienen RLS, y esas queries están más abajo.
            event = await db.get(AIMemoryEvent, event_id)
            entity_type = event.entity_type
            entity_id = event.entity_id

            # 2. Current context (may not exist yet)
            current_ctx: AIEntityContext | None = (await db.execute(
                select(AIEntityContext).where(
                    AIEntityContext.tenant_id == tenant_id,
                    AIEntityContext.entity_type == entity_type,
                    AIEntityContext.entity_id == entity_id,
                )
            )).scalar_one_or_none()

            # 3. Last 20 events for this entity
            recent = (await db.execute(
                select(AIMemoryEvent)
                .where(
                    AIMemoryEvent.tenant_id == tenant_id,
                    AIMemoryEvent.entity_type == entity_type,
                    AIMemoryEvent.entity_id == entity_id,
                )
                .order_by(AIMemoryEvent.created_at.desc())
                .limit(20)
            )).scalars().all()

            now_utc = datetime.now(timezone.utc)

            # 4. LLM call
            parsed: dict[str, Any] | None = None
            try:
                prev_context = (
                    f"summary: {current_ctx.context_summary}\nfacts: {current_ctx.key_facts}"
                    if current_ctx else "Sin contexto previo."
                )
                events_payload = [
                    {
                        "type": e.event_type,
                        "data": e.event_data,
                        "at": e.created_at.isoformat() if e.created_at else None,
                    }
                    for e in recent
                ]
                user_msg = _USER_TMPL.format(
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    prev_context=prev_context,
                    n=len(events_payload),
                    events_json=json.dumps(events_payload, ensure_ascii=False, default=str),
                )
                response = await _anthropic.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=600,
                    system=_SYSTEM,
                    messages=[{"role": "user", "content": user_msg}],
                )
                parsed = _extract_json(response.content[0].text)
            except Exception:
                logger.exception(
                    "[ai_memory] LLM failed for %s/%s", entity_type, entity_id
                )

            # 5. Upsert AIEntityContext
            if parsed:
                summary = str(parsed.get("context_summary", ""))[:600]
                key_facts = parsed.get("key_facts", [])
                if not isinstance(key_facts, list):
                    key_facts = []
                sentiment = str(parsed.get("sentiment", "unknown"))
                urgency = max(0, min(100, int(parsed.get("urgency_score", 0))))

                await db.execute(_upsert_stmt({
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "context_summary": summary,
                    "key_facts": key_facts,
                    "sentiment": sentiment,
                    "urgency_score": urgency,
                    "last_interaction": now_utc,
                    "created_at": now_utc,
                    "updated_at": now_utc,
                }))
                await db.commit()

                # 6. AgentSuggestion if urgent
                if urgency > 70:
                    proactive = parsed.get("proactive_suggestion")
                    if proactive and isinstance(proactive, dict):
                        await _create_agent_suggestion(
                            db, tenant_id, entity_type, entity_id, urgency, proactive,
                        )
                        await db.commit()

                return {"status": "ok", "entity_type": entity_type, "entity_id": str(entity_id), "urgency": urgency}
            else:
                # Fallback: only touch last_interaction
                await db.execute(_upsert_stmt({
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "context_summary": current_ctx.context_summary if current_ctx else "",
                    "key_facts": current_ctx.key_facts if current_ctx else [],
                    "sentiment": current_ctx.sentiment if current_ctx else "unknown",
                    "urgency_score": current_ctx.urgency_score if current_ctx else 0,
                    "last_interaction": now_utc,
                    "created_at": now_utc,
                    "updated_at": now_utc,
                }))
                await db.commit()
                return {"status": "fallback", "entity_type": entity_type, "entity_id": str(entity_id)}

    try:
        return run_async(_run())
    except Exception as exc:
        logger.exception("[ai_memory] task failed for event=%s", memory_event_id)
        raise self.retry(exc=exc)
