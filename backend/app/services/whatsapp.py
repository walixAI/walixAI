import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def process_incoming_message(
    wa_phone: str,
    message_body: str,
    wa_phone_number_id: str,
    message_id: str,
) -> None:
    logger.info(
        "Incoming WhatsApp message: phone=%s phone_number_id=%s message_id=%s body=%r",
        wa_phone,
        wa_phone_number_id,
        message_id,
        message_body,
    )


class WhatsAppService:
    BASE_URL = "https://graph.facebook.com/v19.0"
    TIMEOUT_SECONDS = 10.0
    RETRY_DELAY_SECONDS = 1.0

    async def send_text_message(
        self,
        to_phone: str,
        message: str,
        phone_number_id: str,
        token: str,
    ) -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": message},
        }
        return await self._post(phone_number_id, token, payload)

    async def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language: str,
        phone_number_id: str,
        token: str,
    ) -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }
        return await self._post(phone_number_id, token, payload)

    async def mark_as_read(
        self,
        message_id: str,
        phone_number_id: str,
        token: str,
    ) -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        return await self._post(phone_number_id, token, payload)

    async def _post(
        self,
        phone_number_id: str,
        token: str,
        payload: dict[str, Any],
    ) -> bool:
        url = f"{self.BASE_URL}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        for attempt in (1, 2):
            try:
                async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                    response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    return True
                logger.error(
                    "WhatsApp API non-200 (attempt %d): status=%d body=%s",
                    attempt,
                    response.status_code,
                    response.text,
                )
            except httpx.HTTPError as exc:
                logger.error(
                    "WhatsApp API request failed (attempt %d): %s",
                    attempt,
                    exc,
                )

            if attempt == 1:
                await asyncio.sleep(self.RETRY_DELAY_SECONDS)

        return False
