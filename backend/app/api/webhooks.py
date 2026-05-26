import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from sqlalchemy import select

from app.ai.bot_engine import process_message
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis import redis_client
from app.models.tenant import Branch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Meta retries failed deliveries for up to ~24h, so dedup keys live that long.
DEDUP_TTL_SECONDS = 86_400


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

                background_tasks.add_task(
                    process_message,
                    wa_phone=wa_phone,
                    message_body=message_body,
                    branch_id=branch.id,
                    tenant_id=branch.tenant_id,
                    message_id=message_id,
                )

    return {"status": "ok"}
