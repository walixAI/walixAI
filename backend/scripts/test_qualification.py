"""Simula una conversación completa de calificación exitosa contra el backend local.

Envía 4 mensajes al webhook en secuencia (3 s de espera entre cada uno),
luego consulta /api/leads para mostrar el lead resultante con su
qualification_data y qualification_score.

Corre desde backend/:
    .venv/bin/python scripts/test_qualification.py
"""
import hashlib
import hmac
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.core.config import settings

BASE_URL       = "http://localhost:8000"
WEBHOOK_URL    = f"{BASE_URL}/api/webhooks/whatsapp"
PHONE_NUMBER_ID = "PENDIENTE_MTY"   # must match branches.wa_phone_number_id in local DB

# Use a distinct test number so it doesn't collide with other test leads
WA_PHONE = "5215500000001"

MESSAGES = [
    "hola vi su anuncio",
    "tiene 7 años mi hijo",
    "es que lo veo muy chaparro",
    "soy María y estoy en Monterrey",
]

DELAY_SECONDS = 3


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_payload(body: str, message_id: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_TEST",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": f"+{WA_PHONE}",
                                "phone_number_id": PHONE_NUMBER_ID,
                            },
                            "contacts": [{"profile": {"name": "Papá de prueba"}, "wa_id": WA_PHONE}],
                            "messages": [
                                {
                                    "from": WA_PHONE,
                                    "id": message_id,
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def _sign(body: bytes) -> str:
    return hmac.new(
        settings.META_APP_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


def _send_message(client: httpx.Client, body: str, idx: int) -> bool:
    message_id = f"wamid.QUAL_TEST_{uuid.uuid4().hex[:12]}"
    payload = _build_payload(body, message_id)
    raw = json.dumps(payload).encode("utf-8")
    sig = _sign(raw)

    print(f"[{idx}/{len(MESSAGES)}] Enviando: {body!r}")
    resp = client.post(
        WEBHOOK_URL,
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"},
        timeout=30.0,
    )
    status_ok = resp.status_code == 200
    print(f"        → HTTP {resp.status_code} {'✓' if status_ok else '✗ ' + resp.text}")
    return status_ok


def _get_jwt(client: httpx.Client) -> str | None:
    resp = client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "asistente@clinica.com", "password": "walix2026"},
        timeout=10.0,
    )
    if resp.status_code != 200:
        print(f"Login falló ({resp.status_code}): {resp.text}")
        return None
    return resp.json()["access_token"]


def _find_lead(client: httpx.Client, token: str) -> dict | None:
    resp = client.get(
        f"{BASE_URL}/api/leads?all=true",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    if resp.status_code != 200:
        print(f"GET /api/leads falló ({resp.status_code}): {resp.text}")
        return None
    items = resp.json().get("items", [])
    for lead in items:
        if lead["wa_phone"].endswith(WA_PHONE[-10:]):
            return lead
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("Test de calificación end-to-end")
    print(f"Phone: {WA_PHONE}  ·  {len(MESSAGES)} mensajes  ·  delay {DELAY_SECONDS}s")
    print("=" * 60)

    with httpx.Client() as client:
        # 1. Send messages
        for i, msg in enumerate(MESSAGES, start=1):
            ok = _send_message(client, msg, i)
            if not ok:
                print("\nERROR: webhook rechazó el mensaje. ¿Está corriendo el backend?")
                sys.exit(1)
            if i < len(MESSAGES):
                print(f"        Esperando {DELAY_SECONDS}s…")
                time.sleep(DELAY_SECONDS)

        # 2. Wait for qualifier background task
        extra_wait = 5
        print(f"\nEsperando {extra_wait}s para que el qualifier procese el último mensaje…")
        time.sleep(extra_wait)

        # 3. Fetch lead result
        print("\n─── Resultado ───────────────────────────────────────────────")
        token = _get_jwt(client)
        if token is None:
            sys.exit(1)

        lead = _find_lead(client, token)
        if lead is None:
            print(f"Lead con phone={WA_PHONE} no encontrado. ¿Está el PHONE_NUMBER_ID bien configurado?")
            sys.exit(1)

        qd = lead.get("qualification_data") or {}
        score = lead.get("qualification_score")

        print(f"Lead ID       : {lead['id']}")
        print(f"Nombre        : {lead.get('name') or '(sin nombre)'}")
        print(f"Teléfono      : {lead['wa_phone']}")
        print(f"Status        : {lead['status']}")
        print(f"Sentimiento   : {lead['sentiment']}")
        print(f"Score         : {f'{score * 100:.0f}%' if score is not None else 'pendiente'}")
        print()
        print("qualification_data:")
        for key, val in qd.items():
            print(f"  {key:<25} {val}")

        print("\n" + "=" * 60)
        expected = lead["status"] in ("calificado", "en_calificacion")
        print(f"{'✓ PASS' if expected else '✗ FAIL'} — status={lead['status']!r}")


if __name__ == "__main__":
    main()
