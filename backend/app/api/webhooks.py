import hashlib
import hmac
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from sqlalchemy import select, text

from app.ai.bot_engine import process_message
from app.api.internal_wa import handle_internal_command
from app.core.config import settings
from app.core.database import AsyncSessionLocal, set_tenant_context
from app.core.redis import redis_client
from app.models.agent import AgentSuggestion
from app.models.conversation import Conversation, ConversationHandler, ConversationStatus
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.user import User
from app.models.meta_ads import MetaLeadConfig
from app.models.tenant import Branch
from app.services.whatsapp import WhatsAppService, _normalize_mx_phone

_CODE_RE = re.compile(r"^\d{6}$")
_CONFIRM_WORDS = frozenset({"sí", "si", "confirmar"})

logger = logging.getLogger(__name__)
_whatsapp = WhatsAppService()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _try_support_code(wa_phone: str, code: str) -> bool:
    """Background task: attempt to activate a support session via WA code."""
    try:
        from app.api.support import activate_session_by_code
        async with AsyncSessionLocal() as db:
            return await activate_session_by_code(wa_phone, code, db)
    except Exception:
        logger.exception("webhook: support code activation failed wa=%s", wa_phone)
        return False

# Meta retries failed deliveries for up to ~24h, so dedup keys live that long.
DEDUP_TTL_SECONDS = 86_400

META_GRAPH_URL = "https://graph.facebook.com/v19.0"


def _verify_signature(body: bytes, header: str | None, secret: str) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    received = header[len("sha256=") :]
    return hmac.compare_digest(expected, received)


async def _bg_execute_suggestion(suggestion_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Background wrapper — opens its own DB session."""
    try:
        from app.agents.executor import execute_suggestion
        async with AsyncSessionLocal() as db:
            await execute_suggestion(suggestion_id, tenant_id, db)
    except Exception:
        logger.exception("webhook: bg execute failed for suggestion=%s", suggestion_id)


async def _try_confirm_suggestion(
    wa_phone: str,
    branch: "Branch",
    message_body: str,
    background_tasks: BackgroundTasks,
) -> bool:
    """If message is a confirmation word from an internal user, confirm their latest suggestion.

    Returns True if the message was handled (caller should skip normal bot processing).
    """
    if message_body.strip().lower() not in _CONFIRM_WORDS:
        return False

    # Normalize phone: Meta sends 521XXXXXXXXXX, users may store 52XXXXXXXXXX
    normalized = _normalize_mx_phone(wa_phone)

    async with AsyncSessionLocal() as db:
        # Sesión nueva — users/agent_suggestions tienen RLS. branch.tenant_id
        # ya lo conocemos (viene de _try_confirm_suggestion), así que no hace
        # falta ningún lookup pre-tenant acá.
        await set_tenant_context(db, branch.tenant_id)
        user_result = await db.execute(
            select(User).where(
                User.tenant_id == branch.tenant_id,
                User.is_active.is_(True),
                User.wa_phone.in_([wa_phone, normalized]),
            ).limit(1)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            return False

        sugg_result = await db.execute(
            select(AgentSuggestion).where(
                AgentSuggestion.target_user_id == user.id,
                AgentSuggestion.status == "suggested",
            ).order_by(AgentSuggestion.created_at.desc()).limit(1)
        )
        suggestion = sugg_result.scalar_one_or_none()
        if suggestion is None:
            return False

        suggestion.status = "confirmed"
        suggestion.responded_at = datetime.now(timezone.utc)
        await db.commit()
        suggestion_id = suggestion.id

    background_tasks.add_task(_bg_execute_suggestion, suggestion_id, branch.tenant_id)
    logger.info(
        "webhook: suggestion %s confirmed via WA from %s", suggestion_id, wa_phone
    )
    return True


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    if hub_verify_token != settings.META_VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not _verify_signature(raw_body, signature, settings.META_APP_SECRET):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        # Valid signature but unparseable body — log and ack so Meta stops retrying.
        logger.exception("WhatsApp webhook body could not be parsed as JSON")
        return {"status": "ok"}

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            wa_phone_number_id = value.get("metadata", {}).get("phone_number_id")
            messages = value.get("messages", [])
            if not messages or not wa_phone_number_id:
                # Delivery/read receipts (value.statuses) and other event types
                # land here. Nothing to process — ack and move on.
                continue

            # ── Internal Walix WA number ──────────────────────────────────────
            # Messages on the internal number are staff commands, not customer
            # messages — process via AI Bar interpreter, skip branch lookup.
            if (
                settings.WALIX_INTERNAL_WA_NUMBER_ID
                and wa_phone_number_id == settings.WALIX_INTERNAL_WA_NUMBER_ID
            ):
                for message in messages:
                    message_id = message.get("id")
                    wa_phone = message.get("from")
                    message_body = (message.get("text") or {}).get("body")
                    if not message_id or not wa_phone or message_body is None:
                        continue
                    try:
                        claimed = await redis_client.set(
                            f"msg:{message_id}", "1", nx=True, ex=DEDUP_TTL_SECONDS
                        )
                    except Exception:
                        logger.exception("Redis dedup check failed for %s", message_id)
                        claimed = True
                    if not claimed:
                        continue
                    background_tasks.add_task(
                        handle_internal_command,
                        wa_phone=wa_phone,
                        message_body=message_body,
                    )
                continue  # Skip customer-facing branch processing for this change
            # ── End internal number block ─────────────────────────────────────

            # Resolve the branch this WhatsApp number belongs to. One lookup per
            # `change` since all its messages share the same metadata.
            #
            # Pre-tenant lookup: at this point all we have is the phone number
            # ID from Meta's payload — no tenant is known yet, so a plain
            # `SELECT branches WHERE wa_phone_number_id = ...` would never see
            # a row under RLS with a non-bypass runtime role (walix_app).
            # fn_lookup_tenant_by_wa_phone_id (SECURITY DEFINER, migración
            # l7m8n9o0p1q2) resolves just the tenant_id first; once we have
            # it, set_tenant_context unlocks the real SELECT for the full row.
            async with AsyncSessionLocal() as db:
                tenant_id = (
                    await db.execute(
                        text("SELECT fn_lookup_tenant_by_wa_phone_id(:pid)"),
                        {"pid": wa_phone_number_id},
                    )
                ).scalar_one_or_none()

                branch = None
                if tenant_id is not None:
                    await set_tenant_context(db, tenant_id)
                    result = await db.execute(
                        select(Branch).where(
                            Branch.wa_phone_number_id == wa_phone_number_id
                        )
                    )
                    branch = result.scalar_one_or_none()

            if branch is None:
                logger.warning(
                    "Webhook for unknown wa_phone_number_id=%s — dropping %d message(s)",
                    wa_phone_number_id,
                    len(messages),
                )
                continue

            for message in messages:
                message_id = message.get("id")
                wa_phone = message.get("from")
                message_body = (message.get("text") or {}).get("body")

                # Skip non-text messages (audio/image/etc.) — they have no text.body.
                if not message_id or not wa_phone or message_body is None:
                    continue

                # Atomic SET NX EX: truthy when newly claimed, None when another
                # request already processed this message id.
                try:
                    claimed = await redis_client.set(
                        f"msg:{message_id}",
                        "1",
                        nx=True,
                        ex=DEDUP_TTL_SECONDS,
                    )
                except Exception:
                    # Fail-open: if Redis is down, processing a duplicate is
                    # preferable to dropping the message.
                    logger.exception("Redis dedup check failed for %s", message_id)
                    claimed = True

                if not claimed:
                    continue

                # Support code: 6-digit reply from an owner activates a pending session.
                # These messages are not forwarded to the bot.
                if _CODE_RE.match(message_body.strip()):
                    background_tasks.add_task(
                        _try_support_code,
                        wa_phone=wa_phone,
                        code=message_body.strip(),
                    )
                    continue

                # Sprint 6: 'sí'/'si'/'confirmar' from an internal user confirms
                # their latest pending suggestion without going through the bot.
                if await _try_confirm_suggestion(
                    wa_phone, branch, message_body, background_tasks
                ):
                    continue

                background_tasks.add_task(
                    process_message,
                    wa_phone=wa_phone,
                    message_body=message_body,
                    branch_id=branch.id,
                    tenant_id=branch.tenant_id,
                    message_id=message_id,
                )

    return {"status": "ok"}


# ── Meta Lead Ads webhook ──────────────────────────────────────────────────────

async def _fetch_lead_fields(leadgen_id: str, access_token: str) -> dict[str, str]:
    """Calls Meta Graph API and returns a flat {field_name: value} dict."""
    url = f"{META_GRAPH_URL}/{leadgen_id}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params={"access_token": access_token})
        resp.raise_for_status()
        data = resp.json()
    return {
        item["name"]: item["values"][0]
        for item in data.get("field_data", [])
        if item.get("values")
    }


async def _send_meta_lead_welcome(
    lead_id: uuid.UUID, branch_id: uuid.UUID, tenant_id: uuid.UUID
) -> None:
    """Background task: sends the welcome WhatsApp message to a Meta Ads lead."""
    async with AsyncSessionLocal() as db:
        await set_tenant_context(db, tenant_id)
        lead = await db.get(Lead, lead_id)
        branch = await db.get(Branch, branch_id)
        if not lead or not branch or not branch.wa_phone_number_id or not branch.wa_token:
            logger.warning(
                "meta_leads: cannot send welcome — lead=%s branch=%s", lead_id, branch_id
            )
            return

        name = lead.name or "amigo/a"
        message = (
            f"¡Hola {name}! 👋 Gracias por tu interés en la Clínica de Endocrinología Pediátrica.\n\n"
            f"Soy Wali, tu asistente virtual. Vi que nos dejaste tus datos en nuestro anuncio.\n"
            f"¿Me podrías decir cuántos años tiene tu hijo o hija?"
        )
        try:
            await _whatsapp.send_text_message(
                to_phone=lead.wa_phone,
                message=message,
                phone_number_id=branch.wa_phone_number_id,
                token=branch.wa_token,
            )
            logger.info("meta_leads: welcome sent to lead=%s", lead_id)
        except Exception:
            logger.exception("meta_leads: welcome WA send failed for lead=%s", lead_id)


@router.get("/meta-leads")
async def verify_meta_leads_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    if hub_verify_token != settings.META_VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/meta-leads")
async def receive_meta_leads_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not _verify_signature(raw_body, signature, settings.META_APP_SECRET):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.exception("meta_leads: body could not be parsed as JSON")
        return {"status": "ok"}

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue

            value = change.get("value", {})
            page_id = value.get("page_id")
            form_id = str(value.get("form_id", ""))
            leadgen_id = str(value.get("leadgen_id", ""))
            ad_id = str(value.get("ad_id", "")) or None

            if not page_id or not form_id or not leadgen_id:
                logger.warning("meta_leads: incomplete change value: %s", value)
                continue

            # Dedup: Meta may retry the same leadgen_id
            try:
                claimed = await redis_client.set(
                    f"mlead:{leadgen_id}", "1", nx=True, ex=DEDUP_TTL_SECONDS
                )
            except Exception:
                logger.exception("meta_leads: Redis dedup failed for %s", leadgen_id)
                claimed = True

            if not claimed:
                logger.info("meta_leads: duplicate leadgen_id=%s — skipping", leadgen_id)
                continue

            # Look up the config for this page + form. Pre-tenant lookup:
            # page_id es un identificador externo de Meta, sin tenant
            # conocido todavía — fn_lookup_meta_lead_configs_by_page_id
            # (SECURITY DEFINER, migración o0p1q2r3s4t5) devuelve las mismas
            # columnas que el ORM ya leía sin restricción de tenant; la
            # desambiguación final por form_id sigue igual, en Python.
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    text("SELECT * FROM fn_lookup_meta_lead_configs_by_page_id(:pid)"),
                    {"pid": page_id},
                )
                configs = result.fetchall()

            config = next(
                (c for c in configs if form_id in [str(f) for f in (c.form_ids or [])]),
                None,
            )
            if config is None:
                logger.info(
                    "meta_leads: no active config for page_id=%s form_id=%s — ignoring",
                    page_id,
                    form_id,
                )
                continue

            # Fetch lead data from Meta Graph API
            try:
                raw_fields = await _fetch_lead_fields(
                    leadgen_id, config.page_access_token
                )
            except Exception:
                logger.exception(
                    "meta_leads: Graph API call failed for leadgen_id=%s", leadgen_id
                )
                continue

            # Map fields using config.field_mapping
            # field_mapping format: {"wa_phone": "phone_number", "name": "full_name"}
            mapping: dict[str, str] = config.field_mapping or {}
            wa_phone_raw = raw_fields.get(mapping.get("wa_phone", "phone_number"), "")
            name = raw_fields.get(mapping.get("name", "full_name")) or None

            # Normalize phone: strip leading + and non-digit chars
            wa_phone = "".join(c for c in wa_phone_raw if c.isdigit())
            if not wa_phone:
                logger.warning(
                    "meta_leads: no phone extracted for leadgen_id=%s fields=%s",
                    leadgen_id,
                    raw_fields,
                )
                continue

            # Create Lead + Conversation in a single transaction. config.tenant_id
            # ya lo resolvió fn_lookup_meta_lead_configs_by_page_id arriba.
            async with AsyncSessionLocal() as db:
                await set_tenant_context(db, config.tenant_id)
                lead = Lead(
                    branch_id=config.branch_id,
                    tenant_id=config.tenant_id,
                    wa_phone=wa_phone,
                    name=name,
                    source=LeadSource.META_ADS,
                    status=LeadStatus.NUEVO,
                    meta_lead_id=leadgen_id,
                    meta_form_id=form_id,
                    meta_ad_id=ad_id,
                    qualification_data={},
                )
                db.add(lead)
                await db.flush()  # get lead.id

                conversation = Conversation(
                    lead_id=lead.id,
                    branch_id=config.branch_id,
                    status=ConversationStatus.ACTIVE,
                    current_handler=ConversationHandler.BOT,
                )
                db.add(conversation)
                await db.commit()
                lead_id_captured = lead.id
                branch_id_captured = config.branch_id
                tenant_id_captured = config.tenant_id

            logger.info(
                "meta_leads: created lead=%s from leadgen_id=%s page=%s form=%s",
                lead_id_captured,
                leadgen_id,
                page_id,
                form_id,
            )

            background_tasks.add_task(
                _send_meta_lead_welcome,
                lead_id=lead_id_captured,
                branch_id=branch_id_captured,
                tenant_id=tenant_id_captured,
            )

    return {"status": "ok"}
