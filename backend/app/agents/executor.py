"""Suggestion executor: runs the action associated with an approved AgentSuggestion."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityType, LeadActivity
from app.models.agent import AgentSuggestion
from app.models.lead import Lead
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch
from app.models.user import User
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)
_whatsapp = WhatsAppService()


async def execute_suggestion(
    suggestion_id: uuid.UUID, db: AsyncSession
) -> dict[str, Any]:
    """Execute the action for an AgentSuggestion and update its status.

    Raises ValueError for invalid state. Updates status=executed or status=failed.
    """
    suggestion = await db.get(AgentSuggestion, suggestion_id)
    if suggestion is None:
        raise ValueError(f"AgentSuggestion {suggestion_id} not found")
    if suggestion.status not in ("suggested", "accepted", "confirmed"):
        raise ValueError(
            f"Suggestion {suggestion_id} not executable (status={suggestion.status})"
        )

    try:
        result = await _dispatch(suggestion, db)

        # Optionally record a system activity on the lead if the action targets one
        lead_id_raw = (suggestion.action_payload or {}).get("lead_id")
        if lead_id_raw:
            from app.services.activity_service import create_system_activity
            await create_system_activity(
                lead_id=uuid.UUID(lead_id_raw),
                tenant_id=suggestion.tenant_id,
                description=f"Acción de agente ejecutada: {suggestion.suggestion_text[:150]}",
                db=db,
            )

        suggestion.status = "executed"
        suggestion.execution_result = result
        suggestion.responded_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(
            "executor: executed suggestion=%s agent_type=%s",
            suggestion_id, suggestion.agent_type,
        )
        return result
    except Exception as exc:
        suggestion.status = "failed"
        suggestion.error_detail = str(exc)
        suggestion.responded_at = datetime.now(timezone.utc)
        await db.commit()
        logger.exception(
            "executor: failed suggestion=%s agent_type=%s",
            suggestion_id, suggestion.agent_type,
        )
        raise


# ── Dispatch ──────────────────────────────────────────────────────────────────

async def _dispatch(
    suggestion: AgentSuggestion, db: AsyncSession
) -> dict[str, Any]:
    payload = suggestion.action_payload or {}
    t = suggestion.agent_type
    if t == "follow_up":
        return await _exec_follow_up(payload, suggestion.tenant_id, db)
    if t == "pipeline":
        return await _exec_pipeline(payload, suggestion.tenant_id, db)
    if t == "closing":
        return await _exec_closing(payload, suggestion.tenant_id, db)
    if t == "config":
        return await _exec_config(payload, suggestion.tenant_id, db)
    raise ValueError(f"Unknown agent_type: {t}")


# ── Follow-up ─────────────────────────────────────────────────────────────────

async def _exec_follow_up(
    payload: dict[str, Any], tenant_id: uuid.UUID, db: AsyncSession
) -> dict[str, Any]:
    lead_id = uuid.UUID(payload["lead_id"])
    message = str(payload.get("message", ""))

    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise ValueError(f"Lead {lead_id} not found")

    branch = await _get_branch_with_wa(lead.branch_id, db)

    sent = await _whatsapp.send_text_message(
        to_phone=lead.wa_phone,
        message=message,
        phone_number_id=branch.wa_phone_number_id,
        token=branch.wa_token,
    )

    db.add(LeadActivity(
        lead_id=lead_id,
        tenant_id=tenant_id,
        activity_type=ActivityType.REPLY,
        payload={"agent": "follow_up", "message": message, "sent": sent},
    ))
    await db.flush()

    return {"sent": sent, "lead_id": str(lead_id), "message": message}


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def _exec_pipeline(
    payload: dict[str, Any], tenant_id: uuid.UUID, db: AsyncSession
) -> dict[str, Any]:
    action = payload.get("action", "create_task")

    if action == "reassign":
        return await _exec_pipeline_reassign(payload, tenant_id, db)
    if action == "archive_stage":
        return await _exec_pipeline_archive_stage(payload, db)

    # create_task: log an activity as a note for the gerente
    leads_stalled = [
        s["stage_name"]
        for s in payload.get("bottleneck_stages", [])
    ]
    return {
        "action": "create_task",
        "note": f"Revisión de pipeline requerida: etapas estancadas = {leads_stalled}",
    }


async def _exec_pipeline_reassign(
    payload: dict[str, Any], tenant_id: uuid.UUID, db: AsyncSession
) -> dict[str, Any]:
    lead_ids = [uuid.UUID(lid) for lid in payload.get("leads", [])]
    to_asesor_id_raw = payload.get("to_asesor_id")
    if not lead_ids or not to_asesor_id_raw:
        return {"action": "reassign", "reassigned": 0, "reason": "missing leads or to_asesor_id"}

    to_asesor_id = uuid.UUID(to_asesor_id_raw)
    reassigned = 0
    for lead_id in lead_ids:
        lead = await db.get(Lead, lead_id)
        if lead is None:
            continue
        prev_asesor = lead.assigned_to
        lead.assigned_to = to_asesor_id
        db.add(LeadActivity(
            lead_id=lead_id,
            tenant_id=tenant_id,
            activity_type=ActivityType.ASSIGN,
            payload={
                "agent": "pipeline",
                "from_asesor": str(prev_asesor),
                "to_asesor": str(to_asesor_id),
            },
        ))
        reassigned += 1

    await db.flush()
    return {"action": "reassign", "reassigned": reassigned, "to_asesor_id": str(to_asesor_id)}


async def _exec_pipeline_archive_stage(
    payload: dict[str, Any], db: AsyncSession
) -> dict[str, Any]:
    stage_id_raw = (payload.get("action_detail") or {}).get("stage_id") or payload.get("stage_id")
    if not stage_id_raw:
        return {"action": "archive_stage", "archived": False, "reason": "no stage_id"}

    stage = await db.get(PipelineStage, uuid.UUID(stage_id_raw))
    if stage is None:
        return {"action": "archive_stage", "archived": False, "reason": "stage not found"}

    stage.is_active = False
    await db.flush()
    return {"action": "archive_stage", "archived": True, "stage_id": stage_id_raw}


# ── Closing ───────────────────────────────────────────────────────────────────

async def _exec_closing(
    payload: dict[str, Any], tenant_id: uuid.UUID, db: AsyncSession
) -> dict[str, Any]:
    lead_id = uuid.UUID(payload["lead_id"])
    proposal_text = str(payload.get("proposal_text", ""))

    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise ValueError(f"Lead {lead_id} not found")

    branch = await _get_branch_with_wa(lead.branch_id, db)

    sent = await _whatsapp.send_text_message(
        to_phone=lead.wa_phone,
        message=proposal_text,
        phone_number_id=branch.wa_phone_number_id,
        token=branch.wa_token,
    )

    # Log QUOTE activity
    db.add(LeadActivity(
        lead_id=lead_id,
        tenant_id=tenant_id,
        activity_type=ActivityType.QUOTE,
        payload={"agent": "closing", "proposal_text": proposal_text, "sent": sent},
    ))

    # Advance lead to next pipeline stage (by order_index)
    next_stage_id: uuid.UUID | None = None
    if lead.pipeline_stage_id:
        current_stage = await db.get(PipelineStage, lead.pipeline_stage_id)
        if current_stage:
            next_stage_result = await db.execute(
                select(PipelineStage).where(
                    PipelineStage.branch_id == lead.branch_id,
                    PipelineStage.is_active.is_(True),
                    PipelineStage.is_won.is_(False),
                    PipelineStage.order_index > current_stage.order_index,
                ).order_by(PipelineStage.order_index).limit(1)
            )
            next_stage = next_stage_result.scalar_one_or_none()
            if next_stage:
                prev_stage_id = lead.pipeline_stage_id
                lead.pipeline_stage_id = next_stage.id
                next_stage_id = next_stage.id
                db.add(LeadActivity(
                    lead_id=lead_id,
                    tenant_id=tenant_id,
                    activity_type=ActivityType.STAGE_CHANGE,
                    payload={
                        "agent": "closing",
                        "from_stage": str(prev_stage_id),
                        "to_stage": str(next_stage.id),
                    },
                ))

    await db.flush()
    return {
        "sent": sent,
        "lead_id": str(lead_id),
        "proposal_text": proposal_text,
        "advanced_to_stage": str(next_stage_id) if next_stage_id else None,
    }


# ── Config ────────────────────────────────────────────────────────────────────

async def _exec_config(
    payload: dict[str, Any], tenant_id: uuid.UUID, db: AsyncSession
) -> dict[str, Any]:
    action = payload.get("action", "no_action")
    if action != "deactivate_stage":
        return {"action": action, "applied": False}

    # Stage ID may be in action_detail or top-level
    action_detail = payload.get("action_detail") or {}
    stage_id_raw = action_detail.get("stage_id") or payload.get("stage_id")
    if not stage_id_raw:
        # Fall back to first inactive stage from the computed list
        inactive = payload.get("inactive_stages", [])
        if inactive:
            stage_id_raw = inactive[0].get("stage_id")

    if not stage_id_raw:
        return {"action": action, "applied": False, "reason": "no stage_id resolved"}

    stage = await db.get(PipelineStage, uuid.UUID(stage_id_raw))
    if stage is None:
        return {"action": action, "applied": False, "reason": "stage not found"}

    stage.is_active = False
    await db.flush()
    logger.info("executor: deactivated stage=%s name=%s", stage_id_raw, stage.name)
    return {"action": action, "applied": True, "stage_id": stage_id_raw, "stage_name": stage.name}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_branch_with_wa(branch_id: uuid.UUID, db: AsyncSession) -> Branch:
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise ValueError(f"Branch {branch_id} not found")
    if not branch.wa_phone_number_id or not branch.wa_token:
        raise ValueError(f"Branch {branch_id} has no WA credentials")
    return branch
