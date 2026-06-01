import hashlib
import hmac
import json
import logging
import re
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from sqlalchemy import select

from app.ai.bot_engine import process_message
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis import redis_client
from app.models.conversation import Conversation, ConversationHandler, ConversationStatus
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.meta_ads import MetaLeadConfig
from app.models.tenant import Branch
from app.services.whatsapp import WhatsAppService

_CODE_RE = re.compile(r"^\d{6}$")

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

            # Resolve the branch this WhatsApp number belongs to. One lookup per
            # `change` since all its messages share the same metadata.
            async with AsyncSessionLocal() as db:
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


async def _send_meta_lead_welcome(lead_id: uuid.UUID, branch_id: uuid.UUID) -> None:
    """Background task: sends the welcome WhatsApp message to a Meta Ads lead."""
    async with AsyncSessionLocal() as db:
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

            # Look up the config for this page + form
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(MetaLeadConfig).where(
                        MetaLeadConfig.page_id == page_id,
                        MetaLeadConfig.is_active.is_(True),
                    )
                )
                configs = result.scalars().all()

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

            # Create Lead + Conversation in a single transaction
            async with AsyncSessionLocal() as db:
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
            )

    return {"status": "ok"}
