"""Walix proactive alert generator.

Three entry points:
  send_daily_summary(branch_id)    — called by the hourly scheduler job
  send_no_response_alert(lead_id, rule_id) — called by the 30-min unresponded job
  detect_risk(lead, qualification_result, db) — called by qualifier.py after each turn
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.alert import AlertRule
from app.models.conversation import Message
from app.models.lead import Lead, LeadStatus
from app.models.tenant import Branch
from app.models.user import User, UserRole
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)

MX_TZ = ZoneInfo("America/Mexico_City")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_whatsapp = WhatsAppService()


# ── Silence window ─────────────────────────────────────────────────────────────

def _in_silence_window(silence_start: int, silence_end: int) -> bool:
    """Returns True if the current MX hour falls inside the silence window.

    Default window is 21–8 (9 pm to 8 am), which crosses midnight, so:
      silence_start=21, silence_end=8  →  silent when hour >= 21 OR hour < 8
    """
    hour = datetime.now(MX_TZ).hour
    if silence_start > silence_end:  # crosses midnight
        return hour >= silence_start or hour < silence_end
    return silence_start <= hour < silence_end  # same-day window


# ── Risk computation ──────────────────────────────────────────────────────────

def _compute_risk(lead: Lead, qualification_result: dict) -> tuple[float, str]:
    """Returns (risk_score 0-1, risk_reason) from qualification signals."""
    score = 0.0
    reasons: list[str] = []

    sentiment = getattr(lead.sentiment, "value", str(lead.sentiment))
    if sentiment == "negativo":
        score += 0.40
        reasons.append("sentimiento negativo del prospecto")
    elif sentiment == "urgente":
        score += 0.25
        reasons.append("urgencia detectada")

    escalation_reason = qualification_result.get("escalation_reason")
    if escalation_reason:
        score += 0.35
        reasons.append(str(escalation_reason))

    missing = qualification_result.get("missing_fields") or []
    qual_score = qualification_result.get("qualification_score") or 0.0
    if qual_score < 0.4 and len(missing) >= 3:
        score += 0.20
        reasons.append(
            f"calificación baja ({int(qual_score * 100)}%), {len(missing)} campos faltantes"
        )

    return min(round(score, 2), 1.0), "; ".join(reasons) or "sin riesgo significativo"


# ── Claude helpers ─────────────────────────────────────────────────────────────

async def _claude_text(prompt: str, max_tokens: int = 200) -> str:
    """Calls Claude Haiku and returns plain text. Swallows errors gracefully."""
    try:
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception:
        logger.exception("alert_generator: Claude call failed")
        return ""


async def _send_wa(
    to_phone: str, message: str, phone_number_id: str, token: str
) -> bool:
    """Sends a WA message. Returns True on success, False on error."""
    try:
        await _whatsapp.send_text_message(
            to_phone=to_phone,
            message=message,
            phone_number_id=phone_number_id,
            token=token,
        )
        return True
    except Exception:
        logger.exception(
            "alert_generator: WA send failed to=%s phone_number_id=%s",
            to_phone, phone_number_id,
        )
        return False


# ── Daily summary ─────────────────────────────────────────────────────────────

async def send_daily_summary(branch_id: uuid.UUID) -> None:
    """Computes yesterday's stats and sends a personalized summary to each asesor."""
    async with AsyncSessionLocal() as db:
        branch = await db.get(Branch, branch_id)
        if not branch or not branch.is_active:
            return
        if not branch.wa_phone_number_id or not branch.wa_token:
            logger.info("send_daily_summary: branch %s has no WA credentials — skip", branch_id)
            return

        # Yesterday window (MX timezone)
        now_mx = datetime.now(MX_TZ)
        yesterday_start = (now_mx - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).astimezone(timezone.utc)
        yesterday_end = yesterday_start + timedelta(days=1)

        # Stats
        leads_result = await db.execute(
            select(Lead).where(
                Lead.branch_id == branch_id,
                Lead.created_at >= yesterday_start,
                Lead.created_at < yesterday_end,
            )
        )
        leads_yesterday = leads_result.scalars().all()
        total = len(leads_yesterday)
        calificados = sum(
            1 for l in leads_yesterday
            if getattr(l.status, "value", l.status) == "calificado"
        )
        perdidos = sum(
            1 for l in leads_yesterday
            if getattr(l.status, "value", l.status) == "perdido"
        )

        avg_latency_result = await db.execute(
            select(Message.latency_ms).where(
                Message.latency_ms.isnot(None),
                Message.created_at >= yesterday_start,
                Message.created_at < yesterday_end,
            )
        )
        latencies = [r[0] for r in avg_latency_result.fetchall()]
        avg_resp = f"{sum(latencies) / len(latencies) / 1000:.1f}s" if latencies else "N/D"

        stats_text = (
            f"Leads nuevos: {total} | Calificados: {calificados} | "
            f"Perdidos: {perdidos} | Tiempo prom. respuesta: {avg_resp}"
        )

        # Load asesores with wa_phone
        users_result = await db.execute(
            select(User).where(
                User.branch_id == branch_id,
                User.is_active.is_(True),
                User.wa_phone.isnot(None),
            )
        )
        asesores = users_result.scalars().all()
        if not asesores:
            logger.info("send_daily_summary: no asesores with wa_phone in branch %s", branch_id)
            return

        for user in asesores:
            prompt = (
                f"Genera un resumen diario de ventas de WhatsApp para {user.name}, asesor de {branch.name}.\n"
                f"Estadísticas de ayer: {stats_text}\n"
                f"Escribe en español, máximo 4 líneas, tono motivador y profesional. Solo el mensaje."
            )
            message = await _claude_text(prompt, max_tokens=200)
            if not message:
                message = f"📊 Resumen del día — {branch.name}\n{stats_text}"

            await _send_wa(user.wa_phone, message, branch.wa_phone_number_id, branch.wa_token)
            logger.info(
                "send_daily_summary: sent to user=%s branch=%s", user.id, branch_id
            )


# ── No-response alert ─────────────────────────────────────────────────────────

async def send_no_response_alert(lead_id: uuid.UUID, rule_id: uuid.UUID) -> None:
    """Alerts the assigned user about a lead that hasn't responded."""
    async with AsyncSessionLocal() as db:
        lead = await db.get(Lead, lead_id)
        rule = await db.get(AlertRule, rule_id)
        if not lead or not rule:
            return

        # Re-check silence window (guard against timing edge cases)
        if _in_silence_window(rule.silence_start, rule.silence_end):
            return

        # Find recipient: assigned user or first active user in branch
        if lead.assigned_to:
            user = await db.get(User, lead.assigned_to)
        else:
            result = await db.execute(
                select(User).where(
                    User.branch_id == lead.branch_id,
                    User.is_active.is_(True),
                    User.wa_phone.isnot(None),
                ).limit(1)
            )
            user = result.scalar_one_or_none()

        if user is None or not user.wa_phone:
            logger.info(
                "send_no_response_alert: no user with wa_phone for lead %s", lead_id
            )
            return

        branch = await db.get(Branch, lead.branch_id)
        if not branch or not branch.wa_phone_number_id or not branch.wa_token:
            return

        qdata = lead.qualification_data or {}
        qdata_summary = ", ".join(f"{k}: {v}" for k, v in list(qdata.items())[:4]) or "sin datos"
        hours = rule.threshold_hours

        prompt = (
            f"Genera un mensaje de WhatsApp de alerta para {user.name} (asesor de ventas).\n"
            f"Un prospecto lleva {hours}h sin responder.\n"
            f"Lead: {lead.name or lead.wa_phone} | Status: {getattr(lead.status, 'value', lead.status)}\n"
            f"Datos: {qdata_summary}\n"
            f"Escribe en español, máximo 3 líneas, tono profesional y urgente. Solo el mensaje."
        )
        message = await _claude_text(prompt, max_tokens=150)
        if not message:
            message = (
                f"⚠️ Lead sin respuesta hace {hours}h\n"
                f"Prospecto: {lead.name or lead.wa_phone}\n"
                f"Revisa el dashboard para dar seguimiento."
            )

        sent = await _send_wa(user.wa_phone, message, branch.wa_phone_number_id, branch.wa_token)
        if sent:
            lead.last_alert_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info(
                "send_no_response_alert: alerted user=%s for lead=%s", user.id, lead_id
            )


# ── Monthly summary ───────────────────────────────────────────────────────────

async def send_monthly_summary(branch_id: uuid.UUID) -> None:
    """Sends a monthly performance summary to all active asesores."""
    async with AsyncSessionLocal() as db:
        branch = await db.get(Branch, branch_id)
        if not branch or not branch.is_active:
            return
        if not branch.wa_phone_number_id or not branch.wa_token:
            return

        now_mx = datetime.now(MX_TZ)
        # First day of previous month
        if now_mx.month == 1:
            month_start = now_mx.replace(year=now_mx.year - 1, month=12, day=1)
        else:
            month_start = now_mx.replace(month=now_mx.month - 1, day=1)
        month_start = month_start.replace(
            hour=0, minute=0, second=0, microsecond=0
        ).astimezone(timezone.utc)
        month_end = now_mx.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

        leads_result = await db.execute(
            select(Lead).where(
                Lead.branch_id == branch_id,
                Lead.created_at >= month_start,
                Lead.created_at < month_end,
            )
        )
        leads = leads_result.scalars().all()
        total = len(leads)
        calificados = sum(1 for l in leads if getattr(l.status, "value", l.status) == "calificado")
        tasa = f"{calificados / total * 100:.0f}%" if total else "0%"
        month_name = month_start.strftime("%B %Y")

        users_result = await db.execute(
            select(User).where(
                User.branch_id == branch_id,
                User.is_active.is_(True),
                User.wa_phone.isnot(None),
            )
        )
        asesores = users_result.scalars().all()

        for user in asesores:
            prompt = (
                f"Genera un resumen mensual de WhatsApp para {user.name} ({branch.name}).\n"
                f"Mes: {month_name} | Leads: {total} | Calificados: {calificados} | Tasa: {tasa}\n"
                f"Escribe en español, máximo 5 líneas, tono profesional y motivador. Solo el mensaje."
            )
            message = await _claude_text(prompt, max_tokens=250)
            if not message:
                message = (
                    f"📈 Resumen {month_name} — {branch.name}\n"
                    f"Leads: {total} | Calificados: {calificados} | Tasa: {tasa}"
                )
            await _send_wa(user.wa_phone, message, branch.wa_phone_number_id, branch.wa_token)


# ── Risk detection ─────────────────────────────────────────────────────────────

async def detect_risk(
    lead: Lead, qualification_result: dict, db: AsyncSession
) -> None:
    """Computes and persists risk_score/risk_reason. Sends alert if > 0.7."""
    risk_score, risk_reason = _compute_risk(lead, qualification_result)

    changed = lead.risk_score != risk_score
    lead.risk_score = risk_score
    lead.risk_reason = risk_reason

    if not changed and risk_score <= 0.7:
        return

    await db.commit()
    logger.info(
        "detect_risk: lead=%s risk_score=%.2f reason=%s", lead.id, risk_score, risk_reason
    )

    if risk_score > 0.7:
        try:
            await _send_risk_alert(lead, db)
        except Exception:
            logger.exception("detect_risk: risk alert failed for lead %s", lead.id)


async def _send_risk_alert(lead: Lead, db: AsyncSession) -> None:
    """Sends a risk alert to the assigned user. Respects the branch alert_rule silence window."""
    # Load alert rule to check silence window
    rule_result = await db.execute(
        select(AlertRule).where(
            AlertRule.branch_id == lead.branch_id,
            AlertRule.is_active.is_(True),
        ).limit(1)
    )
    rule = rule_result.scalar_one_or_none()
    silence_start, silence_end = (rule.silence_start, rule.silence_end) if rule else (21, 8)

    if _in_silence_window(silence_start, silence_end):
        logger.info("_send_risk_alert: in silence window — skipping lead %s", lead.id)
        return

    # Find recipient
    if lead.assigned_to:
        user = await db.get(User, lead.assigned_to)
    else:
        result = await db.execute(
            select(User).where(
                User.branch_id == lead.branch_id,
                User.is_active.is_(True),
                User.wa_phone.isnot(None),
            ).limit(1)
        )
        user = result.scalar_one_or_none()

    if user is None or not user.wa_phone:
        return

    branch = await db.get(Branch, lead.branch_id)
    if not branch or not branch.wa_phone_number_id or not branch.wa_token:
        return

    prompt = (
        f"Genera un mensaje de WhatsApp de alerta de riesgo para {user.name} (asesor).\n"
        f"Lead: {lead.name or lead.wa_phone} | Riesgo: {int((lead.risk_score or 0) * 100)}%\n"
        f"Razón: {lead.risk_reason}\n"
        f"Escribe en español, máximo 2 líneas, tono urgente. Solo el mensaje."
    )
    message = await _claude_text(prompt, max_tokens=120)
    if not message:
        message = (
            f"🔴 Lead en riesgo ({int((lead.risk_score or 0) * 100)}%)\n"
            f"Prospecto: {lead.name or lead.wa_phone} — {lead.risk_reason}"
        )

    await _send_wa(user.wa_phone, message, branch.wa_phone_number_id, branch.wa_token)
    logger.info("_send_risk_alert: alerted user=%s for lead=%s", user.id, lead.id)
