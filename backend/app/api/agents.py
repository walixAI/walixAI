"""Proactive agent suggestion endpoints for Walix."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import AsyncSessionLocal, get_db
from app.models.agent import AgentSuggestion
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class SuggestionOut(BaseModel):
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


class DismissBody(BaseModel):
    reason: str | None = None


# ── Background task wrapper ────────────────────────────────────────────────────

async def _bg_execute_suggestion(suggestion_id: uuid.UUID) -> None:
    """Opens its own DB session — safe for use with BackgroundTasks."""
    try:
        from app.agents.executor import execute_suggestion
        async with AsyncSessionLocal() as db:
            await execute_suggestion(suggestion_id, db)
    except Exception:
        logger.exception("agents: bg execute failed for suggestion=%s", suggestion_id)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/suggestions", response_model=list[SuggestionOut])
async def list_suggestions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SuggestionOut]:
    """Return suggested (non-expired) items addressed to the current user.

    Expires stale suggestions in-band before returning the active list.
    """
    now = datetime.now(timezone.utc)

    # Expire suggestions past their expiry date in a single bulk UPDATE
    expire_result = await db.execute(
        select(AgentSuggestion).where(
            AgentSuggestion.tenant_id == current_user.tenant_id,
            AgentSuggestion.status == "suggested",
            AgentSuggestion.expires_at < now,
        )
    )
    for s in expire_result.scalars().all():
        s.status = "expired"
    await db.flush()

    # Fetch suggestions visible to this user:
    # - directly addressed (target_user_id == me), OR
    # - broadcast to my role (target_user_id IS NULL AND target_role == my role)
    rows = await db.execute(
        select(AgentSuggestion).where(
            AgentSuggestion.tenant_id == current_user.tenant_id,
            AgentSuggestion.status == "suggested",
            or_(
                AgentSuggestion.target_user_id == current_user.id,
                (AgentSuggestion.target_user_id.is_(None))
                & (AgentSuggestion.target_role == current_user.role.value),
            ),
        ).order_by(AgentSuggestion.created_at.desc())
    )
    suggestions = rows.scalars().all()
    await db.commit()

    return [SuggestionOut.model_validate(s) for s in suggestions]


@router.post(
    "/suggestions/{suggestion_id}/confirm",
    response_model=SuggestionOut,
)
async def confirm_suggestion(
    suggestion_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuggestionOut:
    """Confirm a suggestion: mark as confirmed and queue execution."""
    suggestion = await _get_suggestion_for_user(suggestion_id, current_user, db)

    if suggestion.status not in ("suggested", "accepted"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Suggestion is already {suggestion.status}",
        )

    suggestion.status = "confirmed"
    suggestion.responded_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(suggestion)

    background_tasks.add_task(_bg_execute_suggestion, suggestion.id)
    logger.info(
        "agents: confirmed suggestion=%s agent_type=%s by user=%s",
        suggestion_id, suggestion.agent_type, current_user.id,
    )
    return SuggestionOut.model_validate(suggestion)


@router.post(
    "/suggestions/{suggestion_id}/dismiss",
    response_model=SuggestionOut,
)
async def dismiss_suggestion(
    suggestion_id: uuid.UUID,
    body: DismissBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuggestionOut:
    """Dismiss a suggestion with an optional reason."""
    suggestion = await _get_suggestion_for_user(suggestion_id, current_user, db)

    if suggestion.status not in ("suggested", "accepted"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Suggestion is already {suggestion.status}",
        )

    suggestion.status = "dismissed"
    suggestion.responded_at = datetime.now(timezone.utc)
    if body.reason:
        suggestion.execution_result = {"dismissed_reason": body.reason}

    await db.commit()
    await db.refresh(suggestion)
    logger.info(
        "agents: dismissed suggestion=%s by user=%s reason=%s",
        suggestion_id, current_user.id, body.reason,
    )
    return SuggestionOut.model_validate(suggestion)


# ── Helper ─────────────────────────────────────────────────────────────────────

async def _get_suggestion_for_user(
    suggestion_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> AgentSuggestion:
    """Load suggestion and verify it belongs to the user's tenant."""
    suggestion = await db.get(AgentSuggestion, suggestion_id)
    if suggestion is None or suggestion.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    return suggestion
