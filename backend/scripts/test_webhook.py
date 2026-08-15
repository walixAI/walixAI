"""Send a fake WhatsApp inbound webhook to the local backend.

Builds a Meta-format payload, signs it with HMAC-SHA256 using the value of
META_APP_SECRET, and POSTs to http://localhost:8000/api/webhooks/whatsapp.

Run from the backend/ directory (the script imports app.core.config to read
the same secret your server is using):

    .venv/bin/python scripts/test_webhook.py
"""
import hashlib
import hmac
import json
import sys
import time
import uuid
from pathlib import Path

# Make `app.*` importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# La consola de Windows suele usar cp1252 por default, que no soporta el "→"
# de los prints de abajo — evita un UnicodeEncodeError a mitad del script.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import httpx

from app.core.config import settings

WEBHOOK_URL = "http://localhost:8000/api/webhooks/whatsapp"

# Mexican mobile, CDMX area code 55. Meta sends the phone WITHOUT the leading +
# and historically prefixes Mexican mobiles with "1" after the country code.
WA_PHONE_E164 = "+5215535637687"
WA_PHONE = WA_PHONE_E164.lstrip("+")

# Must match a branch.wa_phone_number_id in the DB so the webhook can resolve
# the branch. seed.py creates the Monterrey branch with this exact value.
PHONE_NUMBER_ID = "PENDIENTE_MTY"

MESSAGE_BODY = "Hola, mi hijo de 9 años está creciendo poco, ¿pueden ayudarme?"


def build_payload(message_body: str, message_id: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID_PLACEHOLDER",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": WA_PHONE_E164,
                                "phone_number_id": PHONE_NUMBER_ID,
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Mamá de prueba"},
                                    "wa_id": WA_PHONE,
                                }
                            ],
                            "messages": [
                                {
                                    "from": WA_PHONE,
                                    "id": message_id,
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": message_body},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def main() -> int:
    message_id = f"wamid.TEST_{uuid.uuid4().hex[:16]}"
    payload = build_payload(MESSAGE_BODY, message_id)
    raw_body = json.dumps(payload).encode("utf-8")
    signature = sign(raw_body, settings.META_APP_SECRET)

    print(f"POST {WEBHOOK_URL}")
    print(f"  phone_number_id  : {PHONE_NUMBER_ID}")
    print(f"  from             : {WA_PHONE}")
    print(f"  message_id       : {message_id}")
    print(f"  body             : {MESSAGE_BODY!r}")
    print(f"  X-Hub-Signature-256: sha256={signature[:32]}…")
    print()

    response = httpx.post(
        WEBHOOK_URL,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
        timeout=30.0,
    )

    print(f"→ HTTP {response.status_code}")
    print(f"→ body : {response.text}")
    if response.status_code == 200:
        print()
        print("OK. The background task is now running. Check uvicorn logs for:")
        print("  • lead created (or reused) for", WA_PHONE)
        print("  • Claude latency_ms and tokens_used")
        print("  • WhatsApp send attempt (will 401 until Branch.wa_token is set)")
        return 0
    else:
        print(f"\n✗ FAIL — se esperaba HTTP 200, got {response.status_code}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
