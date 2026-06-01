"""Internal Walix WhatsApp channel — AI Bar commands via Walix's own WA number.

When a message arrives on WALIX_INTERNAL_WA_NUMBER_ID the webhook calls
handle_internal_command() instead of the customer-facing bot pipeline.

Recognized fast-path commands (case-insensitive):
  "resumen de hoy"   → daily summary for the calling user
  "mis leads"        → leads assigned to the user with stage
  "leads en riesgo"  → leads with risk_score > 0.7 in user's branch

Any other text is forwarded to Claude (Haiku) using the same interpreter
prompt as the AI Bar, with WA-friendly formatting instructions appended.
"""

import json
import logging
import re
from datetime import datetime, timezone

from anthropic import AsyncAnthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.command_interpreter import build_interpreter_prompt, enrich_context
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.lead import Lead, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.user import User
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)

_whatsapp = WhatsAppService()
_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Short month / day names (locale-independent)
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
_DIAS  = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

_SENTIMENT_EMOJI: dict[str, str] = {
    "interesado": "🟢",
    "neutral": "🟡",
    "urgente": "🔴",
    "negativo": "🔴",
}

_ROUTE_URLS: dict[str, str] = {
    "pipeline":  f"{settings.FRONTEND_URL}/pipeline",
    "dashboard": f"{settings.FRONTEND_URL}/dashboard",
    "whatsapp":  f"{settings.FRONTEND_URL}/whatsapp",
    "leads":     f"{settings.FRONTEND_URL}/whatsapp",
    "settings":  f"{settings.FRONTEND_URL}/settings",
}


# ── Public entry point ────────────────────────────────────────────────────────

async def handle_internal_command(wa_phone: str, message_body: str) -> None:
    """Background task: find the Walix user, dispatch command, reply via WA."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(
                User.wa_phone == wa_phone,
                User.is_active.is_(True),
            )
        )
        user = result.scalar_one_or_none()

    if user is None:
        await _send_reply(
            wa_phone,
            "❌ No reconozco este número en Walix.\n"
            "Pide a tu administrador que registre tu teléfono en tu perfil.",
        )
        return

    logger.info(
        "internal_wa: command from user=%s wa=%s msg=%r",
        user.id, wa_phone, message_body[:80],
    )

    async with AsyncSessionLocal() as db:
        text = await _dispatch(message_body.strip(), user, db)

    await _send_reply(wa_phone, text)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _send_reply(wa_phone: str, text: str) -> None:
    if not settings.WALIX_INTERNAL_WA_NUMBER_ID or not settings.WALIX_INTERNAL_WA_TOKEN:
        logger.error("internal_wa: WALIX_INTERNAL_WA_NUMBER_ID / TOKEN not configured")
        return
    try:
        await _whatsapp.send_text_message(
            to_phone=wa_phone,
            message=text,
            phone_number_id=settings.WALIX_INTERNAL_WA_NUMBER_ID,
            token=settings.WALIX_INTERNAL_WA_TOKEN,
        )
    except Exception:
        logger.exception("internal_wa: send_reply failed to %s", wa_phone)


def _today_label() -> str:
    now = datetime.now(timezone.utc)
    return f"{_DIAS[now.weekday()]} {now.day} {_MESES[now.month - 1]}"


async def _batch_stage_names(
    stage_ids: set, db: AsyncSession
) -> dict:
    if not stage_ids:
        return {}
    rows = await db.execute(
        select(PipelineStage.id, PipelineStage.name).where(PipelineStage.id.in_(stage_ids))
    )
    return {row.id: row.name for row in rows.fetchall()}


# ── Command dispatch ──────────────────────────────────────────────────────────

async def _dispatch(message: str, user: User, db: AsyncSession) -> str:
    normalized = message.lower()

    if normalized == "resumen de hoy":
        return await _cmd_resumen_hoy(user, db)
    if normalized in ("mis leads", "mis leads activos"):
        return await _cmd_mis_leads(user, db)
    if normalized in ("leads en riesgo", "leads riesgo", "riesgo"):
        return await _cmd_leads_en_riesgo(user, db)
    if normalized in ("ayuda", "help", "?", "comandos"):
        return _cmd_ayuda()

    return await _cmd_generic(message, user, db)


# ── Fast-path commands ────────────────────────────────────────────────────────

async def _cmd_resumen_hoy(user: User, db: AsyncSession) -> str:
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    branch_filter = (
        [Lead.branch_id == user.branch_id] if user.branch_id
        else [Lead.tenant_id == user.tenant_id]
    )

    leads_today = (
        await db.scalar(
            select(func.count(Lead.id)).where(*branch_filter, Lead.created_at >= today_start)
        )
    ) or 0

    calificados = (
        await db.scalar(
            select(func.count(Lead.id)).where(
                *branch_filter,
                Lead.created_at >= today_start,
                Lead.status == LeadStatus.CALIFICADO,
            )
        )
    ) or 0

    en_riesgo = (
        await db.scalar(
            select(func.count(Lead.id)).where(*branch_filter, Lead.risk_score > 0.7)
        )
    ) or 0

    # My assigned active leads (top 5)
    my_leads_rows = await db.execute(
        select(Lead.name, Lead.wa_phone, Lead.pipeline_stage_id)
        .where(
            Lead.assigned_to == user.id,
            Lead.status != LeadStatus.PERDIDO,
        )
        .order_by(Lead.updated_at.desc())
        .limit(5)
    )
    my_leads = my_leads_rows.fetchall()

    stage_names = await _batch_stage_names(
        {row.pipeline_stage_id for row in my_leads if row.pipeline_stage_id}, db
    )

    lines = [f"📊 *Resumen de hoy — {_today_label()}*\n"]
    lines.append(f"📥 Leads nuevos: {leads_today}")
    lines.append(f"✅ Calificados: {calificados}")
    lines.append(f"⚠️ En riesgo alto: {en_riesgo}")

    if my_leads:
        lines.append(f"\n👤 Mis leads ({len(my_leads)}):")
        for row in my_leads:
            name = row.name or row.wa_phone
            stage = stage_names.get(row.pipeline_stage_id, "Sin etapa")
            lines.append(f"• {name} → {stage}")

    lines.append(f"\n🔗 {_ROUTE_URLS['pipeline']}")
    return "\n".join(lines)


async def _cmd_mis_leads(user: User, db: AsyncSession) -> str:
    rows = await db.execute(
        select(Lead.name, Lead.wa_phone, Lead.pipeline_stage_id, Lead.sentiment)
        .where(
            Lead.assigned_to == user.id,
            Lead.status != LeadStatus.PERDIDO,
        )
        .order_by(Lead.updated_at.desc())
        .limit(10)
    )
    leads = rows.fetchall()

    if not leads:
        return "📋 No tienes leads asignados actualmente."

    stage_names = await _batch_stage_names(
        {row.pipeline_stage_id for row in leads if row.pipeline_stage_id}, db
    )

    lines = [f"📋 *Mis leads asignados ({len(leads)})*\n"]
    for i, row in enumerate(leads, 1):
        name = row.name or row.wa_phone
        stage = stage_names.get(row.pipeline_stage_id, "Sin etapa")
        emoji = _SENTIMENT_EMOJI.get(str(row.sentiment), "🟡")
        lines.append(f"{i}. {name} {emoji}\n   → {stage}")

    lines.append(f"\n🔗 {_ROUTE_URLS['whatsapp']}")
    return "\n".join(lines)


async def _cmd_leads_en_riesgo(user: User, db: AsyncSession) -> str:
    branch_filter = (
        [Lead.branch_id == user.branch_id] if user.branch_id
        else [Lead.tenant_id == user.tenant_id]
    )

    rows = await db.execute(
        select(Lead.name, Lead.wa_phone, Lead.risk_score, Lead.pipeline_stage_id)
        .where(*branch_filter, Lead.risk_score > 0.7)
        .order_by(Lead.risk_score.desc())
        .limit(10)
    )
    leads = rows.fetchall()

    if not leads:
        return "✅ No hay leads en riesgo alto en este momento."

    stage_names = await _batch_stage_names(
        {row.pipeline_stage_id for row in leads if row.pipeline_stage_id}, db
    )

    lines = [f"⚠️ *Leads en riesgo alto ({len(leads)})*\n"]
    for row in leads:
        name = row.name or row.wa_phone
        stage = stage_names.get(row.pipeline_stage_id, "Sin etapa")
        pct = int((row.risk_score or 0) * 100)
        lines.append(f"• {name} — {pct}% riesgo\n  Etapa: {stage}")

    lines.append(f"\n🔗 {_ROUTE_URLS['pipeline']}")
    return "\n".join(lines)


def _cmd_ayuda() -> str:
    return (
        "🤖 *Comandos disponibles:*\n\n"
        "• *resumen de hoy* — Resumen del día\n"
        "• *mis leads* — Tus leads asignados\n"
        "• *leads en riesgo* — Leads con alerta alta\n\n"
        "O escribe cualquier instrucción en lenguaje natural:\n"
        "_'Mueve a María al stage de Propuesta'_\n"
        "_'¿Cuántos leads tengo esta semana?'_\n"
        "_'Asigna el lead de Juan al Dr. García'_"
    )


# ── Generic Claude fallback ───────────────────────────────────────────────────

async def _cmd_generic(message: str, user: User, db: AsyncSession) -> str:
    context: dict = {
        "screen": "whatsapp_internal",
        "channel": "whatsapp",
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "user_name": user.name,
        "user_role": user.role.value if hasattr(user.role, "value") else str(user.role),
    }
    enriched = await enrich_context(context, user, db)

    system_prompt = build_interpreter_prompt(user.role, enriched)
    system_prompt += (
        "\n\nCANAL: WhatsApp interno. "
        "Formatea response_text para WhatsApp móvil: usa emoji como viñetas, "
        "máximo 400 caracteres en response_text, lenguaje directo en español. "
        "Para acciones de tipo navigate, añade el URL completo en response_text "
        f"usando estas rutas base: {json.dumps(_ROUTE_URLS)}."
    )

    try:
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": message}],
        )
        raw_text = response.content[0].text
    except Exception:
        logger.exception("internal_wa: Claude call failed for user=%s", user.id)
        return "❌ No pude procesar tu instrucción. Intenta de nuevo."

    # Parse JSON interpreter response
    try:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        parsed = json.loads(match.group()) if match else {}
    except (ValueError, json.JSONDecodeError, AttributeError):
        # Claude returned free text (shouldn't happen often) — use as-is
        return raw_text[:1000]

    response_text = str(parsed.get("response_text", raw_text[:400]))

    # Append navigate URL if any action requests navigation
    for action in parsed.get("actions") or []:
        if action.get("type") == "navigate":
            dest = action.get("destination", "dashboard")
            url = _ROUTE_URLS.get(dest, f"{settings.FRONTEND_URL}/{dest}")
            response_text += f"\n\n🔗 {url}"
            break

    return response_text[:1500]
