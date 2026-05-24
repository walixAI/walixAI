import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response

from app.core.config import settings
from app.core.redis import redis_client
from app.services.whatsapp import process_incoming_message

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
    if hub_verify_token != settings.META_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not _verify_signature(raw_body, signature, settings.META_WEBHOOK_SECRET):
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
            for message in value.get("messages", []):
                message_id = message.get("id")
                wa_phone = message.get("from")
                message_body = (message.get("text") or {}).get("body")

                # Skip non-text messages (audio/image/status events). The webhook
                # also receives delivery/read receipts under value.statuses — those
                # have no `messages` array and naturally fall through.
                if not message_id or not wa_phone or message_body is None:
                    continue

                # Atomic SET NX EX: only sets if not present; truthy when newly
                # claimed, None when another request already processed this id.
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
                    process_incoming_message,
                    wa_phone=wa_phone,
                    message_body=message_body,
                    wa_phone_number_id=wa_phone_number_id,
                    message_id=message_id,
                )

    return {"status": "ok"}
