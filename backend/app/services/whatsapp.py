import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def normalize_mx_phone(phone: str | None) -> str | None:
    """Canonical WhatsApp-ready MX phone format: 52XXXXXXXXXX (12 digits,
    no +, no leading 1 after the country code, no spaces/dashes/parens).

    This is the SINGLE source of truth for phone normalization across the
    app — every place that creates or looks up a Lead by wa_phone must use
    this (bot_engine.py, contact_executor.py, copilot_tools.py::
    create_contact, app/api/contacts.py, app/api/webhooks.py's Meta Lead
    Ads path). Before this was unified, at least 4 different call sites
    each had their own ad-hoc normalization (or none), producing 3-4
    different stored formats for the exact same real phone number
    (521XXXXXXXXXX, 52XXXXXXXXXX, +52XXXXXXXXXX, +521XXXXXXXXXX) — which is
    exactly how the same real contact ends up with multiple duplicate Lead
    rows. See docs/PERMISSIONS_DRIFT_BACKLOG.md-style hallazgo: duplicate
    leads reported 2026-08-25 for real Utel prospects.

    Handles:
      - Meta's webhook delivers Mexican mobiles as 521XXXXXXXXXX (13
        digits, historical WhatsApp quirk) — the leading 1 after 52 is
        stripped; the Graph API itself rejects that format when sending.
      - Manually-typed numbers (dashboard, Copilot, CSV import) may include
        +, spaces, dashes, parens, or be a bare 10-digit local number with
        no country code — assumed MX, prefixed with 52.

    Returns None for falsy/empty input (never raises on garbage input —
    callers treat None as "no phone provided").
    """
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        return None
    if digits.startswith("521") and len(digits) == 13:
        digits = "52" + digits[3:]
    elif len(digits) == 10:
        digits = "52" + digits
    return digits


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
        to_phone = normalize_mx_phone(to_phone) or to_phone
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
