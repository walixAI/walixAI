import logging

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
