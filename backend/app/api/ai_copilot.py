"""C4 — Copiloto conversacional: endpoints HTTP.

Separado de ai.py (Walix AI Bar) porque son sistemas distintos:
  - ai.py:         one-shot command interpreter, sin historial persistido, sin tool-use nativo
  - ai_copilot.py: sesión conversacional multi-turno, historial en DB, 18 tools nativas

Rutas:
  POST   /api/ai/copilot/chat    — un turno de conversación
  GET    /api/ai/copilot/history — historial de sesión (filtrado por user_id, privado por usuario)
  DELETE /api/ai/copilot/history — borra sesión (≡ "nueva conversación")

Aislamiento de seguridad:
  Todos los endpoints filtran SIEMPRE por user_id == current_user.id.
  Dos usuarios del mismo tenant con session_id="global" nunca ven el historial del otro.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot_engine import run_copilot_turn
from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.ai_memory import AIConversationMessage
from app.models.tenant import Tenant
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["copilot"])

# ── Rate limiter (in-memory, single-process) ───────────────────────────────────
# Works correctly for single-uvicorn deployments. For multi-worker deployments
# replace with a Redis-backed counter (e.g. via slowapi + Redis backend).
_RL_WINDOW_SECS = 60
_RL_MAX_REQUESTS = 20

_rl_lock = asyncio.Lock()
_rl_state: dict[str, list[float]] = defaultdict(list)


async def _check_rate_limit(user_id: str) -> None:
    async with _rl_lock:
        now = time.monotonic()
        _rl_state[user_id] = [t for t in _rl_state[user_id] if now - t < _RL_WINDOW_SECS]
        if len(_rl_state[user_id]) >= _RL_MAX_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiadas solicitudes al Copiloto. Máximo {_RL_MAX_REQUESTS} por minuto.",
            )
        _rl_state[user_id].append(now)


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class CopilotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="global", max_length=100)
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None


class CopilotChatResponse(BaseModel):
    reply: str
    tool_calls_made: list[str]


class CopilotHistoryMessage(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tool_calls: list
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/copilot/chat", response_model=CopilotChatResponse)
async def copilot_chat(
    body: CopilotChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CopilotChatResponse:
    """One conversational turn of the Copiloto."""
    await _check_rate_limit(str(current_user.id))

    tenant = await db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")

    result = await run_copilot_turn(
        message=body.message,
        session_id=body.session_id,
        user=current_user,
        tenant=tenant,
        db=db,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )
    return CopilotChatResponse(**result)


@router.get("/copilot/history", response_model=list[CopilotHistoryMessage])
async def copilot_history(
    session_id: str = Query(..., max_length=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CopilotHistoryMessage]:
    """Last 40 messages of a session.

    Filters by user_id — history is private per user, not shared across a tenant.
    """
    rows = (
        await db.execute(
            select(AIConversationMessage)
            .where(
                AIConversationMessage.session_id == session_id,
                AIConversationMessage.tenant_id == current_user.tenant_id,
                AIConversationMessage.user_id == current_user.id,  # isolation boundary
            )
            .order_by(AIConversationMessage.created_at.asc())
            .limit(40)
        )
    ).scalars().all()
    return [CopilotHistoryMessage.model_validate(r) for r in rows]


@router.delete("/copilot/history", status_code=status.HTTP_204_NO_CONTENT)
async def delete_copilot_history(
    session_id: str = Query(..., max_length=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deletes all messages for a session (equivalent to 'nueva conversación').

    Only deletes rows owned by current_user — cannot clear another user's history.
    """
    await db.execute(
        delete(AIConversationMessage).where(
            AIConversationMessage.session_id == session_id,
            AIConversationMessage.tenant_id == current_user.tenant_id,
            AIConversationMessage.user_id == current_user.id,
        )
    )
    await db.commit()
