"""Prueba end-to-end: onboarding de una inmobiliaria — Sprint 4 T-35

Flujo:
  1. Login como owner → JWT
  2. Crear Company + Branch de prueba en la BD (SQLAlchemy directo; no hay API REST)
  3. POST /api/onboarding/generate  → draft con config generada por Claude
  4. Mostrar config: bot_name, required_fields, primeras 2 etapas
  5. POST /api/onboarding/approve   → activa el bot en la branch
  6. Simular 4 mensajes WhatsApp vía webhook
  7. Consultar lead creado → verificar campos y status

Corre desde backend/:
    .venv/bin/python scripts/test_onboarding.py
"""
import asyncio
import hashlib
import hmac
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.lead import Lead
from app.models.tenant import Branch, Company

# ── Constantes ─────────────────────────────────────────────────────────────────

BASE_URL        = "http://localhost:8000"
WEBHOOK_URL     = f"{BASE_URL}/api/webhooks/whatsapp"

PHONE_NUMBER_ID = "REALTY_TEST_001"   # ID único para esta branch de prueba
WA_PHONE        = "5215544440001"     # Número ficticio del prospecto

COMPANY_NAME    = "Realty Monterrey"
BRANCH_NAME     = "Realty MTY"
INDUSTRY        = "inmobiliaria"

# Credenciales del owner existente en el sistema de prueba.
# El test crea una branch inmobiliaria bajo este mismo tenant para verificar
# que la plataforma soporta múltiples industrias por tenant.
OWNER_CANDIDATES = ["owner@inmobiliaria.com", "admin@clinica.com", "owner@clinica.com"]
PASSWORD         = "walix2026"

BUSINESS_DESCRIPTION = (
    "Somos una inmobiliaria en Monterrey. Vendemos casas y departamentos de 1.5 a "
    "8 millones de pesos en zonas como San Pedro, Valle y Cumbres. Queremos calificar "
    "leads según su presupuesto, zona de interés, tipo de propiedad y si quieren "
    "comprar pronto."
)

MESSAGES = [
    "hola vi su anuncio, busco un departamento de 2 recámaras en San Pedro",
    "mi presupuesto es entre 2.5 y 3.5 millones de pesos",
    "quiero comprar en los próximos 3 meses",
    "mi nombre es Carlos García",
]

DELAY_BETWEEN_MESSAGES = 3   # segundos
POLL_ATTEMPTS           = 20
POLL_INTERVAL           = 3  # segundos

# Campos de la clínica que NO deben aparecer en el lead inmobiliario
CLINIC_FIELD_KEYWORDS = {"child_age", "hijo_edad", "parent_name", "nombre_padre",
                         "motivo_consulta", "diagnosi", "padecimiento", "consulta"}

# ── Helpers de webhook ─────────────────────────────────────────────────────────

def _build_webhook_payload(body: str, message_id: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_REALTY_TEST",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": f"+{WA_PHONE}",
                        "phone_number_id": PHONE_NUMBER_ID,
                    },
                    "contacts": [{"profile": {"name": "Carlos Prospecto"}, "wa_id": WA_PHONE}],
                    "messages": [{
                        "from": WA_PHONE,
                        "id": message_id,
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": body},
                    }],
                },
                "field": "messages",
            }],
        }],
    }


def _sign_webhook(body: bytes) -> str:
    return hmac.new(
        settings.META_APP_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


# ── BD: setup en un único asyncio.run() ───────────────────────────────────────

async def _setup_and_clean(tenant_id: uuid.UUID) -> Branch:
    """Crea o reutiliza Company+Branch y borra el lead de prueba anterior.

    Todo en UNA sesión/event-loop para evitar el error 'Future attached to a
    different loop' que ocurre cuando asyncio.run() se llama más de una vez
    en el mismo proceso (cada llamada crea y cierra su propio event loop, pero
    el pool de asyncpg queda ligado al primero).
    """
    async with AsyncSessionLocal() as db:
        # 1. Buscar o crear branch
        result = await db.execute(
            select(Branch).where(
                Branch.tenant_id == tenant_id,
                Branch.name == BRANCH_NAME,
            )
        )
        branch = result.scalar_one_or_none()

        if branch is None:
            comp_result = await db.execute(
                select(Company).where(
                    Company.tenant_id == tenant_id,
                    Company.name == COMPANY_NAME,
                )
            )
            company = comp_result.scalar_one_or_none()
            if not company:
                company = Company(
                    tenant_id=tenant_id,
                    name=COMPANY_NAME,
                    industry=INDUSTRY,
                )
                db.add(company)
                await db.flush()

            branch = Branch(
                company_id=company.id,
                tenant_id=tenant_id,
                name=BRANCH_NAME,
                industry=INDUSTRY,
                wa_phone_number_id=PHONE_NUMBER_ID,
                onboarding_status="pending",
            )
            db.add(branch)
            await db.flush()
        elif branch.wa_phone_number_id != PHONE_NUMBER_ID:
            branch.wa_phone_number_id = PHONE_NUMBER_ID

        # 2. Limpiar lead de prueba anterior (polling arranca desde cero)
        await db.execute(
            delete(Lead).where(
                Lead.branch_id == branch.id,
                Lead.wa_phone == WA_PHONE,
            )
        )

        await db.commit()
        await db.refresh(branch)
        return branch


# ── Helpers HTTP ───────────────────────────────────────────────────────────────

def _login(client: httpx.Client) -> tuple[str, str]:
    """Intenta login con los candidatos; devuelve (token, tenant_id)."""
    for email in OWNER_CANDIDATES:
        resp = client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": PASSWORD},
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["access_token"], data["user"]["tenant_id"]
    raise SystemExit(f"❌ Login fallido. Candidatos: {OWNER_CANDIDATES}")


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    line = f"  {mark} {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return ok


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    passed = 0
    failed = 0

    def record(ok: bool) -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    print("=" * 65)
    print("  T-35 · Onboarding inmobiliaria — prueba end-to-end")
    print("=" * 65)

    with httpx.Client(timeout=60.0) as client:

        # ── 1. Login ───────────────────────────────────────────────────────────
        print("\n[1/7] Login como owner")
        token, tenant_id_str = _login(client)
        tenant_id = uuid.UUID(tenant_id_str)
        print(f"  ✓ autenticado  tenant_id={tenant_id_str[:8]}…")

        # ── 2. Crear company + branch + limpiar lead anterior ─────────────────
        print(f"\n[2/7] Crear Company '{COMPANY_NAME}' + Branch '{BRANCH_NAME}'")
        branch = asyncio.run(_setup_and_clean(tenant_id))
        branch_id = str(branch.id)
        print(f"  ✓ branch_id={branch_id[:8]}…  wa_phone_number_id={PHONE_NUMBER_ID}")

        # ── 3. Generar configuración con IA ────────────────────────────────────
        print(f"\n[3/7] POST /api/onboarding/generate  (industry={INDUSTRY})")
        print("  Llamando a Claude Sonnet… esto puede tomar ~10 s")
        gen_resp = client.post(
            f"{BASE_URL}/api/onboarding/generate",
            json={
                "branch_id": branch_id,
                "business_description": BUSINESS_DESCRIPTION,
                "industry": INDUSTRY,
            },
            headers=_headers(token),
        )
        ok_gen = gen_resp.status_code == 201
        record(_check("generate respondió 201", ok_gen, f"HTTP {gen_resp.status_code}"))
        if not ok_gen:
            print(f"  Respuesta: {gen_resp.text[:300]}")
            sys.exit(1)

        draft = gen_resp.json()
        draft_id      = draft["id"]
        gen_config    = draft["generated_config"]
        bot_persona   = gen_config.get("bot_persona", {})
        qualification = gen_config.get("qualification", {})
        pipeline      = gen_config.get("pipeline_stages", [])
        req_fields    = qualification.get("required_fields", [])

        # ── 4. Mostrar config generada ─────────────────────────────────────────
        print("\n[4/7] Config generada:")
        print(f"  Bot name         : {bot_persona.get('name', '?')}")
        print(f"  Industria        : {INDUSTRY}")
        print("  required_fields  :", ", ".join(f["name"] for f in req_fields) or "(vacío)")
        sorted_stages = sorted(pipeline, key=lambda s: s.get("order_index", 99))
        print("  Pipeline (1-2)   :", "  →  ".join(
            f"{s['name']}" for s in sorted_stages[:2]
        ) or "(vacío)")

        # Diagnóstico: verificar que la sección qualification tiene los keys fijos
        _required_qual_keys = ("prompt_template", "objective", "criteria",
                               "disqualifiers", "escalation_triggers", "status_map", "sentiment_map")
        missing_keys = [k for k in _required_qual_keys if not qualification.get(k)]
        if missing_keys:
            print(f"  ⚠  qualification le faltan keys: {missing_keys}")
        else:
            print(f"  ✓ qualification tiene todos los keys fijos")

        # ── 5. Aprobar configuración ───────────────────────────────────────────
        print("\n[5/7] POST /api/onboarding/approve")
        appr_resp = client.post(
            f"{BASE_URL}/api/onboarding/approve",
            json={"draft_id": draft_id},
            headers=_headers(token),
        )
        ok_approve = appr_resp.status_code == 200
        record(_check("approve respondió 200", ok_approve, f"HTTP {appr_resp.status_code}"))
        if not ok_approve:
            print(f"  Respuesta: {appr_resp.text[:300]}")
            sys.exit(1)
        print(f"  ✓ onboarding_status={appr_resp.json().get('onboarding_status')!r}")

        # ── 6. Simular conversación vía webhook ────────────────────────────────
        print(f"\n[6/7] Enviando {len(MESSAGES)} mensajes (delay {DELAY_BETWEEN_MESSAGES}s)")
        print(f"  Lead previo eliminado en el paso 2")
        all_msgs_ok = True
        for i, msg in enumerate(MESSAGES, 1):
            mid = f"wamid.REALTY_{uuid.uuid4().hex[:12]}"
            payload = _build_webhook_payload(msg, mid)
            raw     = json.dumps(payload).encode("utf-8")
            sig     = _sign_webhook(raw)

            resp = client.post(
                WEBHOOK_URL,
                content=raw,
                headers={"Content-Type": "application/json",
                         "X-Hub-Signature-256": f"sha256={sig}",
                         "Connection": "close"},
                timeout=30.0,
            )
            msg_ok = resp.status_code == 200
            if not msg_ok:
                all_msgs_ok = False
            print(f"  {'✓' if msg_ok else '✗'} [{i}/{len(MESSAGES)}] {msg!r}  →  HTTP {resp.status_code}")
            if i < len(MESSAGES):
                time.sleep(DELAY_BETWEEN_MESSAGES)

        record(all_msgs_ok)

        # ── 7. Verificar lead ──────────────────────────────────────────────────
        print(f"\n[7/7] Consultando lead  (poll hasta {POLL_ATTEMPTS}×{POLL_INTERVAL}s)")

        lead = None
        for attempt in range(POLL_ATTEMPTS):
            time.sleep(POLL_INTERVAL)
            leads_resp = client.get(
                f"{BASE_URL}/api/leads?all=true",
                headers=_headers(token),
            )
            if leads_resp.status_code != 200:
                continue
            items = leads_resp.json().get("items", [])
            match = next(
                (it for it in items if it["wa_phone"].endswith(WA_PHONE[-10:])), None
            )
            if not match:
                print(f"  [{attempt+1}/{POLL_ATTEMPTS}] lead aún no encontrado…")
                continue
            # Obtener detalle completo
            detail_resp = client.get(
                f"{BASE_URL}/api/leads/{match['id']}",
                headers=_headers(token),
            )
            if detail_resp.status_code == 200:
                lead = detail_resp.json()
            else:
                lead = match
            status = lead.get("status", "nuevo")
            print(f"  [{attempt+1}/{POLL_ATTEMPTS}] status={status!r}")
            if status not in ("nuevo", "en_calificacion"):
                break

        print()
        if lead is None:
            print("  ✗ Lead no encontrado. ¿Está PHONE_NUMBER_ID registrado en la branch?")
            sys.exit(1)

        # Mostrar datos del lead
        qd = lead.get("qualification_data") or {}
        print(f"  Lead ID    : {lead['id']}")
        print(f"  Nombre     : {lead.get('name') or '(sin nombre)'}")
        print(f"  Status     : {lead['status']}")
        print(f"  Sentimiento: {lead['sentiment']}")
        score = lead.get("qualification_score")
        print(f"  Score      : {f'{score * 100:.0f}%' if score is not None else 'pendiente'}")
        print()
        print("  qualification_data:")
        for key, val in qd.items():
            print(f"    {key:<30} {val}")

        # ── Verificaciones ─────────────────────────────────────────────────────
        print()
        print("  ─── Verificaciones ───────────────────────────────────────────")

        # a) el qualifier corrió y avanzó el status (mínimo en_calificacion)
        is_cal = lead["status"] in ("calificado", "en_calificacion", "escalado")
        record(_check("qualifier corrió (status != 'nuevo')", is_cal, lead["status"]))

        # b) qualification_data no está vacío
        has_qd = len(qd) > 0
        record(_check("qualification_data tiene datos", has_qd, f"{len(qd)} campos"))

        # c) Los required_fields del config generado aparecen en qd
        field_names = [f["name"] for f in req_fields]
        present     = [f for f in field_names if f in qd]
        missing     = [f for f in field_names if f not in qd]
        fields_ok   = len(present) >= max(1, len(field_names) // 2)
        record(_check(
            f"required_fields presentes en qd ({len(present)}/{len(field_names)})",
            fields_ok,
            f"presentes={present}  faltantes={missing}" if missing else "",
        ))

        # d) Ningún campo de la clínica aparece en los datos
        clinic_present = {k for k in qd if any(ck in k.lower() for ck in CLINIC_FIELD_KEYWORDS)}
        no_clinic = len(clinic_present) == 0
        record(_check(
            "no hay campos de la clínica en los datos",
            no_clinic,
            f"encontrados: {clinic_present}" if clinic_present else "",
        ))

        # e) El bot_name es diferente al de la clínica
        bot_name_gen   = bot_persona.get("name", "")
        different_bot  = bot_name_gen.lower() not in ("wali", "")
        record(_check(
            f"bot_name es distinto al de la clínica",
            different_bot,
            f"generado={bot_name_gen!r}",
        ))

        # f) Al menos 4 pipeline stages generados
        enough_stages = len(pipeline) >= 4
        record(_check(
            f"pipeline tiene ≥4 etapas",
            enough_stages,
            f"generadas={len(pipeline)}",
        ))

    # ── Resumen ────────────────────────────────────────────────────────────────
    total = passed + failed
    print()
    print("=" * 65)
    print(f"  Resultado: {passed}/{total} verificaciones pasaron")
    if failed == 0:
        print("  🎉 PASS — onboarding inmobiliaria funciona correctamente")
    else:
        print(f"  ⚠  FAIL — {failed} verificación(es) fallaron")
    print("=" * 65)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
