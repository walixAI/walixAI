"""Automation repository endpoints — management view of all AgentSuggestions."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import AsyncSessionLocal, get_db
from app.models.agent import AgentSuggestion
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automations", tags=["automations"])

_GERENTE_PLUS = {UserRole.GERENTE, UserRole.OWNER, UserRole.IT, UserRole.PLATFORM_OWNER}
_OWNER_PLUS = {UserRole.OWNER, UserRole.IT, UserRole.PLATFORM_OWNER}


# ── Schemas ────────────────────────────────────────────────────────────────────

class AutomationOut(BaseModel):
    id: uuid.UUID
    agent_type: str
    trigger_description: str
    suggestion_text: str
    action_payload: dict[str, Any] | None
    target_role: str
    target_user_id: uuid.UUID | None
    status: str
    execution_result: dict[str, Any] | None
    error_detail: str | None
    responded_at: datetime | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationListResponse(BaseModel):
    items: list[AutomationOut]
    total: int
    page: int
    limit: int


class AutomationPatchBody(BaseModel):
    is_active: bool | None = None
    custom_message: str | None = None


# ── Background task wrapper ────────────────────────────────────────────────────

async def _bg_execute_suggestion(suggestion_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    try:
        from app.agents.executor import execute_suggestion
        async with AsyncSessionLocal() as db:
            await execute_suggestion(suggestion_id, tenant_id, db)
    except Exception:
        logger.exception("automations: bg execute failed for suggestion=%s", suggestion_id)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=AutomationListResponse)
async def list_automations(
    status_filter: str | None = Query(default=None, alias="status"),
    agent_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomationListResponse:
    """List all agent suggestions for the tenant. Requires gerente or above."""
    _require_role(current_user, _GERENTE_PLUS)

    base = select(AgentSuggestion).where(
        AgentSuggestion.tenant_id == current_user.tenant_id
    )
    if status_filter:
        base = base.where(AgentSuggestion.status == status_filter)
    if agent_type:
        base = base.where(AgentSuggestion.agent_type == agent_type)

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    offset = (page - 1) * limit
    rows = await db.execute(
        base.order_by(AgentSuggestion.created_at.desc()).limit(limit).offset(offset)
    )
    items = [AutomationOut.model_validate(s) for s in rows.scalars().all()]

    return AutomationListResponse(items=items, total=total, page=page, limit=limit)


@router.patch("/{suggestion_id}", response_model=AutomationOut)
async def patch_automation(
    suggestion_id: uuid.UUID,
    body: AutomationPatchBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomationOut:
    """Edit a suggestion: disable it or update its message text. Requires owner."""
    _require_role(current_user, _OWNER_PLUS)

    suggestion = await _get_suggestion(suggestion_id, current_user, db)

    if body.is_active is False and suggestion.status == "suggested":
        suggestion.status = "dismissed"
        suggestion.responded_at = datetime.now(timezone.utc)
        suggestion.execution_result = {"dismissed_reason": "disabled by owner"}

    if body.custom_message is not None:
        suggestion.suggestion_text = body.custom_message[:255]
        # If there's a follow_up or closing payload with a message, update it too
        if suggestion.action_payload and "message" in suggestion.action_payload:
            payload = dict(suggestion.action_payload)
            payload["message"] = body.custom_message
            suggestion.action_payload = payload
        elif suggestion.action_payload and "proposal_text" in suggestion.action_payload:
            payload = dict(suggestion.action_payload)
            payload["proposal_text"] = body.custom_message
            suggestion.action_payload = payload

    await db.commit()
    await db.refresh(suggestion)
    return AutomationOut.model_validate(suggestion)


@router.post("/{suggestion_id}/re-execute", response_model=AutomationOut)
async def re_execute_automation(
    suggestion_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomationOut:
    """Re-execute a dismissed or failed suggestion. Requires owner."""
    _require_role(current_user, _OWNER_PLUS)

    suggestion = await _get_suggestion(suggestion_id, current_user, db)

    if suggestion.status not in ("dismissed", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only dismissed or failed suggestions can be re-executed (current: {suggestion.status})",
        )

    suggestion.status = "confirmed"
    suggestion.error_detail = None
    suggestion.responded_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(suggestion)

    background_tasks.add_task(_bg_execute_suggestion, suggestion.id, current_user.tenant_id)
    logger.info(
        "automations: re-execute queued suggestion=%s by owner=%s",
        suggestion_id, current_user.id,
    )
    return AutomationOut.model_validate(suggestion)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _require_role(user: User, allowed: set[UserRole]) -> None:
    if user.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )


async def _get_suggestion(
    suggestion_id: uuid.UUID, user: User, db: AsyncSession
) -> AgentSuggestion:
    suggestion = await db.get(AgentSuggestion, suggestion_id)
    if suggestion is None or suggestion.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    return suggestion
