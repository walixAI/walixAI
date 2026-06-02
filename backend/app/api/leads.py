import json
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.models.scoring import LeadScore

MX_TZ = ZoneInfo("America/Mexico_City")

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.redis import redis_client
from app.models.activity import ActivityType, LeadActivity
from app.models.pipeline import PipelineStage
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.core.config import settings
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.tenant import Branch
from app.models.user import User, UserRole  # noqa: F401  (also used by get_current_user)
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)
_whatsapp = WhatsAppService()

router = APIRouter(prefix="/leads", tags=["leads"])
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])

_CONV_HISTORY_TTL = 86_400   # 24 h — must match bot_engine.py
_CONV_HISTORY_MAX = 8        # must match bot_engine.py

_RETURN_TO_BOT_MESSAGE = (
    "Ahora te atenderá nuestro asistente Wali nuevamente. "
    "Si necesitas hablar con nosotros directamente, escribe 'asistente' en cualquier momento."
)


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class LeadListItem(BaseModel):
    id: uuid.UUID
    wa_phone: str
    name: str | None
    status: LeadStatus
    sentiment: LeadSentiment
    source: LeadSource
    assigned_to: uuid.UUID | None
    contact_phone: str | None
    qualification_score: float | None = None
    pipeline_stage_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadListResponse(BaseModel):
    items: list[LeadListItem]
    total: int
    limit: int
    offset: int


class LeadDetail(LeadListItem):
    branch_id: uuid.UUID
    tenant_id: uuid.UUID
    qualification_data: dict[str, Any]
    qualification_score: float | None = None
    assigned_to_name: str | None = None
    handoff_at: datetime | None = None
    handoff_by: uuid.UUID | None = None
    meta_lead_id: str | None = None
    meta_form_id: str | None = None
    meta_ad_id: str | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    tokens_used: int | None
    latency_ms: int | None
    created_at: datetime
    sent_by_user_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class ConversationOut(BaseModel):
    conversation_id: uuid.UUID | None
    status: ConversationStatus | None
    current_handler: ConversationHandler | None
    handler_user_id: uuid.UUID | None
    messages: list[MessageOut]


class LeadWithConversation(LeadDetail):
    """Extended response that embeds conversation state — used by handoff endpoints."""
    conversation: ConversationOut | None = None


class LeadStatusUpdate(BaseModel):
    status: LeadStatus
    note: str | None = None


class SendMessageBody(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El mensaje no puede estar vacío")
        return v


class ReplyBody(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El mensaje no puede estar vacío")
        return v


class ReplyResponse(BaseModel):
    message_id: uuid.UUID
    sent_at: datetime
    status: str


class StageUpdateBody(BaseModel):
    stage_id: uuid.UUID
    moved_by: str = "manual"  # "manual" | "ai_command" | "auto"


class LeadStageOut(LeadDetail):
    stage_name: str | None = None
    stage_slug: str | None = None


class AssignBody(BaseModel):
    user_id: uuid.UUID


class UserBrief(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str

    model_config = ConfigDict(from_attributes=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

_MULTI_BRANCH_ROLES = (UserRole.OWNER, UserRole.IT)


def _require_branch(user: User) -> uuid.UUID:
    if user.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no branch assigned",
        )
    return user.branch_id


async def _get_lead_accessible(
    db: AsyncSession, lead_id: uuid.UUID, user: User
) -> Lead:
    """Fetch a lead the user is allowed to see.

    Owner/IT: any lead in their tenant.
    Others: only leads in their own branch.
    """
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    if user.role in _MULTI_BRANCH_ROLES:
        if lead.tenant_id != user.tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    else:
        branch_id = _require_branch(user)
        if lead.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


async def _get_active_conversation(
    db: AsyncSession, lead_id: uuid.UUID
) -> Conversation | None:
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.lead_id == lead_id,
            Conversation.status != ConversationStatus.CLOSED,
        )
        .order_by(Conversation.started_at.desc())
    )
    return result.scalars().first()


async def _build_conversation_out(
    db: AsyncSession, conversation: Conversation
) -> ConversationOut:
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    messages = [MessageOut.model_validate(m) for m in msg_result.scalars().all()]
    return ConversationOut(
        conversation_id=conversation.id,
        status=conversation.status,
        current_handler=conversation.current_handler,
        handler_user_id=conversation.handler_user_id,
        messages=messages,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=LeadListResponse)
async def list_leads(
    status_filter: LeadStatus | None = Query(default=None, alias="status"),
    on_date: date | None = Query(default=None, alias="date"),
    all_dates: bool = Query(default=False, alias="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadListResponse:
    if current_user.role in _MULTI_BRANCH_ROLES:
        base = select(Lead).where(Lead.tenant_id == current_user.tenant_id)
    else:
        branch_id = _require_branch(current_user)
        base = select(Lead).where(Lead.branch_id == branch_id)

    if not all_dates:
        target_date = on_date or datetime.now(MX_TZ).date()
        start = datetime.combine(target_date, time.min, tzinfo=MX_TZ)
        end = start + timedelta(days=1)
        base = base.where(Lead.created_at >= start, Lead.created_at < end)

    if status_filter is not None:
        base = base.where(Lead.status == status_filter)

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    rows = await db.execute(
        base.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
    )
    items = [LeadListItem.model_validate(lead) for lead in rows.scalars().all()]

    return LeadListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadDetail:
    lead = await _get_lead_accessible(db, lead_id, current_user)
    detail = LeadDetail.model_validate(lead)
    if lead.assigned_to:
        assignee = await db.get(User, lead.assigned_to)
        detail.assigned_to_name = assignee.name if assignee else None
    return detail


@router.get("/{lead_id}/conversation", response_model=ConversationOut)
async def get_lead_conversation(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    await _get_lead_accessible(db, lead_id, current_user)

    conversation = await _get_active_conversation(db, lead_id)
    if conversation is None:
        return ConversationOut(
            conversation_id=None, status=None, current_handler=None,
            handler_user_id=None, messages=[]
        )

    return await _build_conversation_out(db, conversation)


@router.put("/{lead_id}/status", response_model=LeadDetail)
async def update_lead_status(
    lead_id: uuid.UUID,
    body: LeadStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadDetail:
    lead = await _get_lead_accessible(db, lead_id, current_user)

    previous = lead.status
    history_entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "from_status": previous.value,
        "to_status": body.status.value,
        "note": body.note,
        "by_user_id": str(current_user.id),
    }
    # JSONB columns aren't mutation-tracked by default — reassign so SQLAlchemy
    # emits an UPDATE.
    existing = dict(lead.qualification_data or {})
    existing["status_history"] = [*existing.get("status_history", []), history_entry]
    lead.qualification_data = existing
    lead.status = body.status

    db.add(LeadActivity(
        lead_id=lead.id,
        tenant_id=lead.tenant_id,
        actor_id=current_user.id,
        activity_type=ActivityType.STATUS_CHANGE,
        payload={"from": previous.value, "to": body.status.value, "note": body.note},
    ))

    await db.commit()
    await db.refresh(lead)
    return LeadDetail.model_validate(lead)


@router.post("/{lead_id}/handoff", response_model=LeadWithConversation)
async def handoff_lead(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadWithConversation:
    """Asistente toma control manual de la conversación."""
    lead = await _get_lead_accessible(db, lead_id, current_user)

    conversation = await _get_active_conversation(db, lead.id)
    if conversation is not None:
        conversation.current_handler = ConversationHandler.HUMAN
        conversation.handler_user_id = current_user.id
        conversation.status = ConversationStatus.HANDOFF

    now = datetime.now(timezone.utc)
    lead.status = LeadStatus.ESCALADO
    lead.handoff_at = now
    lead.handoff_by = current_user.id

    db.add(LeadActivity(
        lead_id=lead.id,
        tenant_id=lead.tenant_id,
        actor_id=current_user.id,
        activity_type=ActivityType.HANDOFF,
        payload={
            "conversation_id": str(conversation.id) if conversation else None,
        },
    ))

    await db.commit()
    await db.refresh(lead)

    detail = LeadWithConversation.model_validate(lead)
    if lead.assigned_to:
        assignee = await db.get(User, lead.assigned_to)
        detail.assigned_to_name = assignee.name if assignee else None
    if conversation:
        await db.refresh(conversation)
        detail.conversation = await _build_conversation_out(db, conversation)

    return detail


@router.post("/{lead_id}/return-to-bot", response_model=LeadWithConversation)
async def return_to_bot(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadWithConversation:
    """Devuelve el control al bot y notifica al lead via WhatsApp."""
    lead = await _get_lead_accessible(db, lead_id, current_user)

    conversation = await _get_active_conversation(db, lead.id)

    if conversation is None or conversation.current_handler != ConversationHandler.HUMAN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La conversación no está bajo control humano",
        )

    conversation.current_handler = ConversationHandler.BOT
    conversation.handler_user_id = None
    conversation.status = ConversationStatus.ACTIVE
    lead.status = LeadStatus.EN_CALIFICACION

    db.add(LeadActivity(
        lead_id=lead.id,
        tenant_id=lead.tenant_id,
        actor_id=current_user.id,
        activity_type=ActivityType.RETURN_TO_BOT,
        payload={"conversation_id": str(conversation.id)},
    ))

    await db.commit()
    await db.refresh(lead)
    await db.refresh(conversation)

    # Send transition message through the branch's WhatsApp number.
    branch = await db.get(Branch, lead.branch_id)
    if branch and branch.wa_phone_number_id and branch.wa_token:
        try:
            await _whatsapp.send_text_message(
                to_phone=lead.wa_phone,
                message=_RETURN_TO_BOT_MESSAGE,
                phone_number_id=branch.wa_phone_number_id,
                token=branch.wa_token,
            )
        except Exception:
            logger.exception("return_to_bot: WA delivery failed for lead %s", lead_id)
    else:
        logger.warning("return_to_bot: branch %s has no WA credentials", lead.branch_id)

    detail = LeadWithConversation.model_validate(lead)
    if lead.assigned_to:
        assignee = await db.get(User, lead.assigned_to)
        detail.assigned_to_name = assignee.name if assignee else None
    detail.conversation = await _build_conversation_out(db, conversation)

    return detail


@router.patch("/{lead_id}/stage", response_model=LeadStageOut)
async def update_lead_stage(
    lead_id: uuid.UUID,
    body: StageUpdateBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadStageOut:
    """Moves a lead to a different pipeline stage (drag-and-drop or AI command)."""
    lead = await _get_lead_accessible(db, lead_id, current_user)

    stage = await db.get(PipelineStage, body.stage_id)
    if stage is None or stage.branch_id != lead.branch_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stage not found in this branch",
        )

    old_stage_id = lead.pipeline_stage_id
    lead.pipeline_stage_id = stage.id

    # Sync lead status with terminal stage semantics
    if stage.is_won:
        lead.status = LeadStatus.CALIFICADO
    elif stage.is_lost:
        lead.status = LeadStatus.PERDIDO

    moved_by = body.moved_by if body.moved_by in ("manual", "ai_command", "auto") else "manual"
    db.add(LeadActivity(
        lead_id=lead.id,
        tenant_id=lead.tenant_id,
        actor_id=current_user.id,
        activity_type=ActivityType.STAGE_CHANGE,
        payload={
            "from_stage_id": str(old_stage_id) if old_stage_id else None,
            "to_stage_id": str(stage.id),
            "to_stage_name": stage.name,
            "moved_by": moved_by,
        },
    ))

    await db.commit()
    await db.refresh(lead)

    out = LeadStageOut.model_validate(lead)
    out.stage_name = stage.name
    out.stage_slug = stage.slug
    if lead.assigned_to:
        assignee = await db.get(User, lead.assigned_to)
        out.assigned_to_name = assignee.name if assignee else None
    return out


@router.post("/{lead_id}/messages", response_model=MessageOut)
async def send_message(
    lead_id: uuid.UUID,
    body: SendMessageBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Send a message from the asistente through the clinic's WhatsApp number."""
    lead = await _get_lead_accessible(db, lead_id, current_user)

    conversation = await _get_active_conversation(db, lead_id)
    if conversation is None or conversation.current_handler != ConversationHandler.HUMAN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La conversación no está bajo control humano",
        )

    msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=body.text.strip(),
        sent_by_user_id=current_user.id,
    )
    db.add(msg)

    db.add(LeadActivity(
        lead_id=lead.id,
        tenant_id=lead.tenant_id,
        actor_id=current_user.id,
        activity_type=ActivityType.REPLY,
        payload={"preview": body.text.strip()[:120]},
    ))

    await db.flush()

    branch = await db.get(Branch, lead.branch_id)
    if branch and branch.wa_phone_number_id and branch.wa_token:
        try:
            await _whatsapp.send_text_message(
                to_phone=lead.wa_phone,
                message=body.text.strip(),
                phone_number_id=branch.wa_phone_number_id,
                token=branch.wa_token,
            )
        except Exception:
            logger.exception("send_message: WA delivery failed for lead %s", lead_id)
    else:
        logger.warning("send_message: branch %s has no WA credentials", lead.branch_id)

    await db.commit()
    await db.refresh(msg)
    return MessageOut.model_validate(msg)


@router.post("/{lead_id}/reply", response_model=ReplyResponse, status_code=status.HTTP_201_CREATED)
async def reply_to_lead(
    lead_id: uuid.UUID,
    body: ReplyBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReplyResponse:
    """Asistente responde al lead desde el dashboard.

    Diferencias respecto a /messages: error 502 si WhatsApp falla (no silencioso),
    actualiza last_message_at y agrega el mensaje al historial de Redis para que
    el bot tenga contexto completo si retoma el control.
    """
    lead = await _get_lead_accessible(db, lead_id, current_user)

    # 1. Conversación activa
    conversation = await _get_active_conversation(db, lead.id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay conversación activa para este lead",
        )

    # 2. Verificar control humano
    if conversation.current_handler != ConversationHandler.HUMAN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El bot tiene el control. Usa /handoff primero.",
        )

    # 3. Credenciales del branch
    branch = await db.get(Branch, lead.branch_id)
    if not branch or not branch.wa_phone_number_id or not branch.wa_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El branch no tiene credenciales de WhatsApp configuradas",
        )

    text = body.message.strip()

    # 4. Enviar por WhatsApp — error 502 si falla (no silencioso)
    try:
        await _whatsapp.send_text_message(
            to_phone=lead.wa_phone,
            message=text,
            phone_number_id=branch.wa_phone_number_id,
            token=branch.wa_token,
        )
    except Exception as exc:
        logger.exception("reply: WA delivery failed for lead %s", lead_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WhatsApp no pudo entregar el mensaje: {exc}",
        ) from exc

    # 5. Persistir mensaje
    now = datetime.now(timezone.utc)
    msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=text,
        sent_by_user_id=current_user.id,
    )
    db.add(msg)

    # 6. Auditoría
    db.add(LeadActivity(
        lead_id=lead.id,
        tenant_id=lead.tenant_id,
        actor_id=current_user.id,
        activity_type=ActivityType.REPLY,
        payload={"preview": text[:120]},
    ))

    # 7. Actualizar timestamp de último mensaje
    conversation.last_message_at = now

    await db.flush()   # get msg.id before commit
    msg_id = msg.id
    await db.commit()

    # 8. Agregar al historial de Redis para continuidad del bot
    history_key = f"conv:{conversation.id}"
    try:
        raw = await redis_client.get(history_key)
        history: list[dict] = json.loads(raw) if raw else []
        history.append({"role": "assistant", "content": text})
        history = history[-_CONV_HISTORY_MAX:]
        await redis_client.set(history_key, json.dumps(history), ex=_CONV_HISTORY_TTL)
    except Exception:
        # Redis failure must not block the response — message was already sent and persisted.
        logger.exception("reply: failed to update Redis history for conv %s", conversation.id)

    return ReplyResponse(message_id=msg_id, sent_at=now, status="sent")


@router.get("/{lead_id}/assignees", response_model=list[UserBrief])
async def list_assignees(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserBrief]:
    """Returns active users in the branch to whom a lead can be assigned.

    Doctors appear first, then asesores, then the rest.
    """
    lead = await _get_lead_accessible(db, lead_id, current_user)

    rows = await db.execute(
        select(User)
        .where(User.branch_id == lead.branch_id, User.is_active.is_(True))
        .order_by(User.role, User.name)
    )
    users = rows.scalars().all()

    role_order = {UserRole.DOCTOR: 0, UserRole.ASESOR: 1, UserRole.GERENTE: 2}
    sorted_users = sorted(users, key=lambda u: role_order.get(u.role, 9))
    return [UserBrief.model_validate(u) for u in sorted_users]


@router.post("/{lead_id}/assign", response_model=LeadDetail)
async def assign_lead(
    lead_id: uuid.UUID,
    body: AssignBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadDetail:
    """Assigns a lead to a user (doctor or asesor) and notifies them via WhatsApp."""
    lead = await _get_lead_accessible(db, lead_id, current_user)

    assignee = await db.get(User, body.user_id)
    if assignee is None or assignee.branch_id != lead.branch_id or not assignee.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado en esta sucursal",
        )

    old_assigned_to = lead.assigned_to
    lead.assigned_to = body.user_id

    db.add(LeadActivity(
        lead_id=lead.id,
        tenant_id=lead.tenant_id,
        actor_id=current_user.id,
        activity_type=ActivityType.ASSIGN,
        payload={
            "from": str(old_assigned_to) if old_assigned_to else None,
            "to": str(body.user_id),
            "assigned_to_name": assignee.name,
        },
    ))

    await db.commit()
    await db.refresh(lead)

    # Notify the assignee via WhatsApp if they have a wa_phone configured.
    if assignee.wa_phone:
        branch = await db.get(Branch, lead.branch_id)
        if branch and branch.wa_phone_number_id and branch.wa_token:
            qdata = lead.qualification_data or {}
            parent_name = qdata.get("parent_name") or lead.name or "—"
            child_age = qdata.get("child_age")
            age_str = f"{child_age} años" if child_age is not None else "—"
            consultation_reason = qdata.get("consultation_reason") or "—"
            parent_city = qdata.get("parent_city") or "—"
            score = lead.qualification_score
            score_str = f"{score * 100:.0f}%" if score is not None else "—"

            wa_message = (
                f"🩺 Lead asignado — Walix\n\n"
                f"Hola {assignee.name}, tienes un nuevo lead asignado:\n\n"
                f"Nombre: {parent_name}\n"
                f"Edad del niño: {age_str}\n"
                f"Motivo: {consultation_reason}\n"
                f"Ciudad: {parent_city}\n"
                f"Calificación: {score_str}\n\n"
                f"Conversación completa:\n"
                f"{settings.FRONTEND_URL}/dashboard/leads/{lead.id}"
            )
            try:
                await _whatsapp.send_text_message(
                    to_phone=assignee.wa_phone,
                    message=wa_message,
                    phone_number_id=branch.wa_phone_number_id,
                    token=branch.wa_token,
                )
            except Exception:
                logger.exception(
                    "assign_lead: WA notification failed for user %s", assignee.id
                )
        else:
            logger.warning(
                "assign_lead: branch %s has no WA credentials — skipping notification",
                lead.branch_id,
            )
    else:
        logger.info(
            "assign_lead: user %s has no wa_phone — skipping WA notification", assignee.id
        )

    detail = LeadDetail.model_validate(lead)
    detail.assigned_to_name = assignee.name
    return detail


# ── Score endpoints ────────────────────────────────────────────────────────────

class ScoreHistoryItem(BaseModel):
    id: uuid.UUID
    score: int
    main_reason: str
    calculated_at: datetime
    positive_factors: dict = {}
    negative_factors: dict = {}
    model_config = ConfigDict(from_attributes=True)


class LeadScoreOut(BaseModel):
    current_score: int | None
    current_score_trend: str | None
    history: list[ScoreHistoryItem]


@router.get("/{lead_id}/score", response_model=LeadScoreOut)
async def get_lead_score(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadScoreOut:
    lead = await _get_lead_accessible(db, lead_id, current_user)

    rows = await db.execute(
        select(LeadScore)
        .where(LeadScore.lead_id == lead_id)
        .order_by(LeadScore.calculated_at.desc())
        .limit(5)
    )
    history = [ScoreHistoryItem.model_validate(r) for r in rows.scalars().all()]

    return LeadScoreOut(
        current_score=lead.current_score,
        current_score_trend=lead.current_score_trend,
        history=history,
    )


_MANUAL_ACTIVITY_TYPES = {
    ActivityType.CALL,
    ActivityType.TASK,
    ActivityType.QUOTE,
    ActivityType.NOTE,
}


class ActivityCreateBody(BaseModel):
    activity_type: str
    payload: dict[str, Any] = {}

    @field_validator("activity_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        allowed = {"call", "task", "quote", "note"}
        if v not in allowed:
            raise ValueError(f"activity_type must be one of {allowed}")
        return v


class ActivityOut(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    actor_id: uuid.UUID | None
    activity_type: str
    payload: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskCompleteBody(BaseModel):
    completed: bool = True


@router.post("/{lead_id}/activity", response_model=ActivityOut, status_code=status.HTTP_201_CREATED)
async def create_activity(
    lead_id: uuid.UUID,
    body: ActivityCreateBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityOut:
    lead = await _get_lead_accessible(db, lead_id, current_user)

    activity = LeadActivity(
        lead_id=lead.id,
        tenant_id=lead.tenant_id,
        actor_id=current_user.id,
        activity_type=body.activity_type,
        payload=body.payload or {},
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return ActivityOut.model_validate(activity)


@router.get("/{lead_id}/tasks", response_model=list[ActivityOut])
async def list_tasks(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityOut]:
    await _get_lead_accessible(db, lead_id, current_user)

    rows = await db.execute(
        select(LeadActivity)
        .where(
            LeadActivity.lead_id == lead_id,
            LeadActivity.activity_type == ActivityType.TASK.value,
        )
        .order_by(LeadActivity.created_at.desc())
    )
    return [ActivityOut.model_validate(a) for a in rows.scalars().all()]


@router.post("/{lead_id}/score/recalculate", response_model=dict)
async def recalculate_lead_score(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lead = await _get_lead_accessible(db, lead_id, current_user)

    from app.services.prediction_service import calculate_lead_score
    result = await calculate_lead_score(lead.id, lead.tenant_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error calculando el score — revisa los logs del servidor",
        )
    return result


# ── Tasks router (PATCH /tasks/{task_id}) ─────────────────────────────────────

@tasks_router.patch("/{task_id}", response_model=ActivityOut)
async def complete_task(
    task_id: uuid.UUID,
    body: TaskCompleteBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityOut:
    """Mark a task activity as completed (or uncompleted)."""
    activity = await db.get(LeadActivity, task_id)
    if activity is None or activity.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if getattr(activity.activity_type, "value", activity.activity_type) != "task":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Activity is not a task",
        )

    new_payload = dict(activity.payload or {})
    new_payload["completed"] = body.completed
    if body.completed:
        new_payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    else:
        new_payload.pop("completed_at", None)
    activity.payload = new_payload

    await db.commit()
    await db.refresh(activity)
    return ActivityOut.model_validate(activity)
