"""Sprint 3 T-25 — test_meta_leads.py

Pruebas del flujo Meta Lead Ads:

  1. Verifica que el endpoint rechaza firmas HMAC inválidas (403).
  2. Envía un webhook con firma válida y page_id/form_id conocidos (200).
  3. Nota: la tarea de fondo llama a la Graph API de Meta con el leadgen_id;
     sin credenciales reales la llamada falla silenciosamente y el lead NO
     se crea vía webhook.  El paso 4 inserta el lead directamente en la BD
     para verificar el modelo de datos.
  4. Verifica que un lead con source='meta_ads' aparece en la API.

Corre desde backend/ (con el backend levantado en localhost:8000):
    .venv/bin/python scripts/test_meta_leads.py
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

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.meta_ads import MetaLeadConfig
from app.models.tenant import Branch, Tenant

BASE_URL = "http://localhost:8000"
WEBHOOK_URL = f"{BASE_URL}/api/webhooks/meta-leads"

# Test identifiers — must match the MetaLeadConfig created in step 0
TEST_PAGE_ID = "TEST_PAGE_12345"
TEST_FORM_ID = "TEST_FORM_67890"

# Owner credentials
OWNER_EMAIL = "owner@clinica.com"
PASSWORD = "walix2026"
# Asistente for leads list verification
ASISTENTE_EMAIL = "asistente@clinica.com"

_ok = 0
_fail = 0


def ok(label: str) -> None:
    global _ok
    _ok += 1
    print(f"  ✓ {label}")


def fail(label: str, detail: str = "") -> None:
    global _fail
    _fail += 1
    suffix = f" — {detail}" if detail else ""
    print(f"  ✗ {label}{suffix}")


def check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        ok(label)
    else:
        fail(label, detail)
    return condition


def _sign(body: bytes) -> str:
    return hmac.new(
        settings.META_APP_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


def _build_meta_leads_payload(page_id: str, form_id: str, leadgen_id: str) -> dict:
    return {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "time": int(time.time()),
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "page_id": page_id,
                            "form_id": form_id,
                            "leadgen_id": leadgen_id,
                            "ad_id": f"AD_{uuid.uuid4().hex[:8]}",
                        },
                    }
                ],
            }
        ],
    }


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _ensure_meta_config(page_id: str, form_id: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Upserts a test MetaLeadConfig in the first available branch.

    Returns (branch_id, tenant_id).
    """
    async with AsyncSessionLocal() as db:
        tenant = (
            await db.execute(
                select(Tenant).where(Tenant.email == "admin@clinica.com")
            )
        ).scalar_one_or_none()
        if tenant is None:
            raise RuntimeError("Tenant no encontrado — corre seed.py primero")

        branch = (
            await db.execute(
                select(Branch)
                .where(Branch.tenant_id == tenant.id)
                .order_by(Branch.name)
                .limit(1)
            )
        ).scalar_one_or_none()
        if branch is None:
            raise RuntimeError("Sin sucursales — corre seed.py primero")

        # Upsert MetaLeadConfig
        existing = (
            await db.execute(
                select(MetaLeadConfig).where(
                    MetaLeadConfig.branch_id == branch.id,
                    MetaLeadConfig.page_id == page_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.form_ids = [form_id]
            existing.is_active = True
        else:
            db.add(
                MetaLeadConfig(
                    id=uuid.uuid4(),
                    branch_id=branch.id,
                    tenant_id=tenant.id,
                    page_id=page_id,
                    page_access_token="TEST_TOKEN_NOT_REAL",
                    form_ids=[form_id],
                    field_mapping={
                        "wa_phone": "phone_number",
                        "name": "full_name",
                    },
                    is_active=True,
                )
            )
        await db.commit()
        return branch.id, tenant.id


async def _insert_meta_lead(branch_id: uuid.UUID, tenant_id: uuid.UUID) -> uuid.UUID:
    """Inserts a lead with source=META_ADS directly in the DB to verify the model."""
    async with AsyncSessionLocal() as db:
        lead = Lead(
            branch_id=branch_id,
            tenant_id=tenant_id,
            wa_phone=f"52155{uuid.uuid4().hex[:8]}",
            name="Papá de prueba Meta Ads",
            source=LeadSource.META_ADS,
            status=LeadStatus.NUEVO,
            meta_lead_id=f"LEADGEN_{uuid.uuid4().hex[:12]}",
            meta_form_id=TEST_FORM_ID,
            qualification_data={},
        )
        db.add(lead)
        await db.commit()
        return lead.id


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 62)
    print("Sprint 3 T-25 — test_meta_leads.py")
    print("=" * 62)

    # ── 0. Preparar MetaLeadConfig en BD ──────────────────────────────────────
    print("\n[0] Preparar MetaLeadConfig de prueba en BD")
    try:
        branch_id, tenant_id = await _ensure_meta_config(TEST_PAGE_ID, TEST_FORM_ID)
        ok(f"MetaLeadConfig activo para page_id={TEST_PAGE_ID}")
        print(f"     branch_id={branch_id}")
    except Exception as exc:
        fail("Crear MetaLeadConfig", str(exc))
        return

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:

        # ── 1. Firma inválida → 403 ───────────────────────────────────────────
        print("\n[1] Verificar rechazo de firma HMAC inválida")
        leadgen_id = f"LEADGEN_{uuid.uuid4().hex[:16]}"
        payload = _build_meta_leads_payload(TEST_PAGE_ID, TEST_FORM_ID, leadgen_id)
        raw = json.dumps(payload).encode()

        r = await client.post(
            "/api/webhooks/meta-leads",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalidsignature",
            },
        )
        check("Firma inválida → 403", r.status_code == 403,
              f"HTTP {r.status_code} (se esperaba 403)")

        # ── 2. Firma válida + page/form conocidos → 200 ───────────────────────
        print("\n[2] Webhook con firma válida")
        leadgen_id = f"LEADGEN_{uuid.uuid4().hex[:16]}"
        payload = _build_meta_leads_payload(TEST_PAGE_ID, TEST_FORM_ID, leadgen_id)
        raw = json.dumps(payload).encode()
        sig = _sign(raw)

        print(f"     page_id   : {TEST_PAGE_ID}")
        print(f"     form_id   : {TEST_FORM_ID}")
        print(f"     leadgen_id: {leadgen_id}")
        print(f"     signature : sha256={sig[:32]}…")

        r = await client.post(
            "/api/webhooks/meta-leads",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={sig}",
            },
        )
        check("POST /webhooks/meta-leads 200", r.status_code == 200,
              f"HTTP {r.status_code}: {r.text[:120]}")
        if r.status_code == 200:
            print("     ⚠  La tarea de fondo llama a graph.facebook.com con el leadgen_id;")
            print("        sin token real falla silenciosamente (esperado en local).")

        # ── 3. Lead directo en BD con source=meta_ads ─────────────────────────
        print("\n[3] Insertar lead con source=meta_ads directamente en BD")
        try:
            meta_lead_id = await _insert_meta_lead(branch_id, tenant_id)
            ok(f"Lead insertado: {meta_lead_id}")
        except Exception as exc:
            fail("Insertar lead meta_ads", str(exc))
            return

        # ── 4. Verificar lead aparece en la API ───────────────────────────────
        print("\n[4] Verificar via API que el lead aparece con source='meta_ads'")
        r = await client.post("/api/auth/login",
                              json={"email": ASISTENTE_EMAIL, "password": PASSWORD})
        check("Login asistente 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code != 200:
            return

        token = r.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        r = await client.get("/api/leads", params={"all": "true"}, headers=auth)
        check("GET /leads 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            items = r.json()["items"]
            meta_leads = [l for l in items if l.get("source") == "meta_ads"]
            check(f"Hay leads con source=meta_ads ({len(meta_leads)})",
                  len(meta_leads) > 0, "no se encontraron leads con source=meta_ads")
            if meta_leads:
                newest = meta_leads[0]
                check("source == 'meta_ads'", newest["source"] == "meta_ads",
                      f"got: {newest['source']}")
                print(f"     name  : {newest.get('name')}")
                print(f"     phone : {newest.get('wa_phone')}")
                print(f"     status: {newest.get('status')}")

    # ── Resumen ───────────────────────────────────────────────────────────────
    total = _ok + _fail
    print()
    print("=" * 62)
    print(f"Resultado: {_ok}/{total} checks pasaron")
    if _fail:
        print(f"  {_fail} fallo(s) — revisa los ✗ arriba.")
    else:
        print("  Todos los checks pasaron.")
    print("=" * 62)


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(1 if _fail else 0)
