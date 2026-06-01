"""Support access system for Walix.

Endpoints:
  POST /api/support/request       — soporte user requests access to a tenant
  POST /api/support/verify-code   — activates session after owner confirms code
  POST /api/support/revoke/{id}   — owner revokes an active/pending session

The owner can also confirm via WhatsApp by replying with the 6-digit code;
app/api/webhooks.py intercepts those messages and calls _activate_session_by_code.
"""

import logging
import random
import re
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.support import SupportSession
from app.models.tenant import Branch
from app.models.user import User, UserRole
from app.services.whatsapp import WhatsAppService

router = APIRouter(prefix="/support", tags=["support"])
logger = logging.getLogger(__name__)
_whatsapp = WhatsAppService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class SupportRequestBody(BaseModel):
    tenant_id: uuid.UUID
    reason: str
    scope: Literal["readonly", "readwrite"]
    requested_duration_hours: int = Field(ge=2, le=8)


class SupportRequestOut(BaseModel):
    session_id: uuid.UUID
    message: str


class VerifyCodeBody(BaseModel):
    session_id: uuid.UUID
    code: str


class VerifyCodeOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str


# ── Internal helpers ─────────────────────────────────────────────────────────

def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


async def _branch_with_wa(tenant_id: uuid.UUID, db: AsyncSession) -> Branch | None:
    result = await db.execute(
        select(Branch).where(
            Branch.tenant_id == tenant_id,
            Branch.is_active.is_(True),
            Branch.wa_phone_number_id.isnot(None),
            Branch.wa_token.isnot(None),
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _tenant_owner(tenant_id: uuid.UUID, db: AsyncSession) -> User | None:
    result = await db.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.role == UserRole.OWNER,
            User.is_active.is_(True),
            User.wa_phone.isnot(None),
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _send_wa_safe(
    to_phone: str, message: str, phone_number_id: str, token: str, context: str
) -> None:
    try:
        await _whatsapp.send_text_message(
            to_phone=to_phone,
            message=message,
            phone_number_id=phone_number_id,
            token=token,
        )
    except Exception:
        logger.exception("support: WA send failed [%s]", context)


def _issue_support_token(session: SupportSession) -> str:
    return create_access_token(
        data={
            "sub": str(session.support_user_id),
            "tenant_id": str(session.tenant_id),
            "scope": session.scope,
            "support_session_id": str(session.id),
        },
        expires_at=session.session_expires_at,
    )


# ── Public helper called from webhooks ───────────────────────────────────────

async def activate_session_by_code(
    wa_phone: str, code: str, db: AsyncSession
) -> bool:
    """Tries to activate a support session via a WA message from the owner.

    Returns True if a session was activated, False otherwise.
    Designed to be called from the webhook handler before bot processing.
    """
    if not re.fullmatch(r"\d{6}", code):
        return False

    now = datetime.now(timezone.utc)

    # Find a pending session for a tenant whose owner's wa_phone matches
    result = await db.execute(
        select(SupportSession).where(
            SupportSession.status == "pending",
            SupportSession.code_expires_at > now,
        )
    )
    pending_sessions = result.scalars().all()

    for session in pending_sessions:
        owner = await _tenant_owner(session.tenant_id, db)
        if owner is None or owner.wa_phone != wa_phone:
            continue
        if session.access_code != code:
            continue

        # Match found — activate
        session.status = "active"
        session.authorized_by = owner.id
        session.session_expires_at = now + timedelta(hours=session.requested_duration_hours)
        await db.commit()
        await db.refresh(session)

        logger.info(
            "support: session %s activated via WA code from owner %s", session.id, owner.id
        )

        # Notify the support user
        branch = await _branch_with_wa(session.tenant_id, db)
        supp_user = await db.get(User, session.support_user_id)
        if branch and supp_user and supp_user.wa_phone:
            expires_str = session.session_expires_at.strftime("%H:%M")
            await _send_wa_safe(
                to_phone=supp_user.wa_phone,
                message=(
                    f"✅ Acceso de soporte activado.\n"
                    f"Alcance: {session.scope} | Expira a las {expires_str}."
                ),
                phone_number_id=branch.wa_phone_number_id,
                token=branch.wa_token,
                context=f"notify-supp-user session={session.id}",
            )
        return True

    return False


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/request", response_model=SupportRequestOut, status_code=status.HTTP_201_CREATED)
async def request_support_access(
    body: SupportRequestBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupportRequestOut:
    if current_user.role != UserRole.SOPORTE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo ejecutivos de soporte")

    owner = await _tenant_owner(body.tenant_id, db)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant no encontrado o sin owner con WhatsApp configurado",
        )

    branch = await _branch_with_wa(body.tenant_id, db)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El tenant no tiene sucursal con WhatsApp configurado",
        )

    code = _generate_code()
    now = datetime.now(timezone.utc)

    session = SupportSession(
        support_user_id=current_user.id,
        tenant_id=body.tenant_id,
        reason=body.reason,
        access_code=code,
        code_expires_at=now + timedelta(minutes=15),
        scope=body.scope,
        status="pending",
        requested_duration_hours=body.requested_duration_hours,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    scope_label = "Solo lectura" if body.scope == "readonly" else "Lectura y escritura"
    await _send_wa_safe(
        to_phone=owner.wa_phone,
        message=(
            f"🔐 Solicitud de acceso a soporte Walix\n"
            f"El ejecutivo *{current_user.name}* solicita acceso a tu cuenta.\n"
            f"Motivo: {body.reason}\n"
            f"Alcance: {scope_label}\n"
            f"Código: *{code}*\n"
            f"Válido 15 minutos. Responde con el código para autorizar."
        ),
        phone_number_id=branch.wa_phone_number_id,
        token=branch.wa_token,
        context=f"send-code owner={owner.id} session={session.id}",
    )

    logger.info(
        "support: session %s created tenant=%s soporte=%s",
        session.id, body.tenant_id, current_user.id,
    )
    return SupportRequestOut(session_id=session.id, message="Código enviado al owner por WhatsApp")


@router.post("/verify-code", response_model=VerifyCodeOut)
async def verify_support_code(
    body: VerifyCodeBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VerifyCodeOut:
    session = await db.get(SupportSession, body.session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesión no encontrada")

    if session.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sesión en estado '{session.status}'",
        )

    now = datetime.now(timezone.utc)
    code_exp = session.code_expires_at
    if code_exp.tzinfo is None:
        code_exp = code_exp.replace(tzinfo=timezone.utc)
    if code_exp < now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Código expirado")

    if session.access_code != body.code:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código incorrecto")

    session.status = "active"
    session.authorized_by = current_user.id
    session.session_expires_at = now + timedelta(hours=session.requested_duration_hours)
    await db.commit()
    await db.refresh(session)

    # Notify support user
    branch = await _branch_with_wa(session.tenant_id, db)
    supp_user = await db.get(User, session.support_user_id)
    if branch and supp_user and supp_user.wa_phone:
        expires_str = session.session_expires_at.strftime("%H:%M")
        await _send_wa_safe(
            to_phone=supp_user.wa_phone,
            message=(
                f"✅ Acceso de soporte activado.\n"
                f"Alcance: {session.scope} | Expira a las {expires_str}."
            ),
            phone_number_id=branch.wa_phone_number_id,
            token=branch.wa_token,
            context=f"notify-supp session={session.id}",
        )

    logger.info("support: session %s activated via API by user %s", session.id, current_user.id)

    return VerifyCodeOut(
        access_token=_issue_support_token(session),
        expires_at=session.session_expires_at.isoformat(),
    )


@router.post("/revoke/{session_id}", status_code=status.HTTP_200_OK)
async def revoke_support_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    session = await db.get(SupportSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesión no encontrada")

    if current_user.role != UserRole.OWNER or current_user.tenant_id != session.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el owner del tenant puede revocar",
        )

    if session.status not in ("pending", "active"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sesión ya en estado '{session.status}'",
        )

    session.status = "revoked"
    await db.commit()

    # Notify support user
    branch = await _branch_with_wa(session.tenant_id, db)
    supp_user = await db.get(User, session.support_user_id)
    if branch and supp_user and supp_user.wa_phone:
        await _send_wa_safe(
            to_phone=supp_user.wa_phone,
            message="🚫 Tu acceso de soporte fue revocado por el propietario de la cuenta.",
            phone_number_id=branch.wa_phone_number_id,
            token=branch.wa_token,
            context=f"revoke-notify session={session.id}",
        )

    logger.info("support: session %s revoked by owner %s", session.id, current_user.id)
    return {"status": "revoked", "session_id": str(session.id)}
