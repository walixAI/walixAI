"""audit_utel_qualification_data.py — PASO 2 y PASO 3 del prompt Utel branch.industry.

SOLO LECTURA — no modifica ningún lead. Reporta el alcance de la
contaminación de datos causada por branch.industry=None (ya corregido por
scripts/admin/fix_utel_branch_industry.py) para que Walix decida cómo
remediarla.

PASO 2: para todos los leads reales de Utel (source=whatsapp_inbound, sin
el tag "Demo — Borrable"), reporta cuántos tienen claves del esquema de
salud (parent_name/child_age/consultation_reason/parent_city) con datos
reales, y pega el qualification_data completo de Antonio Torres y Erick.

PASO 3: pega la conversación completa de Antonio Torres + su
qualification_data + lead.company, para diagnosticar la recomendación de
Diseño de Videojuegos a un contacto de despacho contable.

Uso:
    .venv/Scripts/python.exe scripts/admin/audit_utel_qualification_data.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation, Message
from app.models.lead import Lead, LeadSource
from app.models.tenant import Tenant

TENANT_EMAIL = "admin@utel.walix.mx"
DEMO_TAG_NAME = "Demo — Borrable"

_SALUD_KEYS = ["parent_name", "child_age", "consultation_reason", "parent_city"]

TARGET_PHONES = {
    "Antonio Torres": "525535637687",
    "Erick": "525517278186",
}


async def main() -> int:
    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.email == TENANT_EMAIL)
        )).scalar_one_or_none()
        if tenant is None:
            print(f"✗ No existe tenant {TENANT_EMAIL!r}.")
            return 1

        leads = (await db.execute(
            select(Lead).where(
                Lead.tenant_id == tenant.id,
                Lead.source == LeadSource.WHATSAPP_INBOUND,
                Lead.deleted_at.is_(None),
            ).options(selectinload(Lead.tags))
        )).scalars().unique().all()

        print("=" * 70)
        print("  PASO 2 — Auditoría de datos ya contaminados (SOLO LECTURA)")
        print("=" * 70)
        print(f"\nTotal leads source=whatsapp_inbound (incl. demo, antes de filtrar): {len(leads)}")

        real_leads: list[Lead] = []
        demo_leads: list[Lead] = []
        for lead in leads:
            tag_names = {t.name for t in lead.tags}
            if DEMO_TAG_NAME in tag_names:
                demo_leads.append(lead)
            else:
                real_leads.append(lead)

        print(f"Con tag {DEMO_TAG_NAME!r} (excluidos del análisis): {len(demo_leads)}")
        print(f"Leads reales a analizar: {len(real_leads)}")

        n_with_salud_keys = 0
        n_empty = 0
        print("\nDetalle por lead:")
        for lead in real_leads:
            qdata = lead.qualification_data or {}
            salud_keys_present = {k: qdata[k] for k in _SALUD_KEYS if qdata.get(k) is not None}
            if not qdata:
                n_empty += 1
            if salud_keys_present:
                n_with_salud_keys += 1
            print(
                f"  lead_id={lead.id} wa_phone={lead.wa_phone!r} name={lead.name!r} "
                f"company={lead.company!r} status={lead.status.value} "
                f"qualification_data_keys={list(qdata.keys())}"
            )
            if salud_keys_present:
                print(f"      -> claves de esquema salud con dato real: {salud_keys_present}")

        print(f"\nResumen: {n_with_salud_keys}/{len(real_leads)} leads reales tienen >=1 clave del "
              f"esquema de salud con dato real. {n_empty}/{len(real_leads)} tienen qualification_data vacío.")

        print("\n" + "-" * 70)
        print("  Detalle completo: Antonio Torres y Erick")
        print("-" * 70)
        target_leads: dict[str, Lead] = {}
        for name, phone in TARGET_PHONES.items():
            match = next((l for l in leads if l.wa_phone == phone), None)
            if match is None:
                print(f"\n✗ No se encontró lead con wa_phone={phone!r} ({name})")
                continue
            target_leads[name] = match
            print(f"\n{name} (lead_id={match.id}, wa_phone={match.wa_phone}):")
            print(f"  lead.company = {match.company!r}")
            print(f"  qualification_data = {json.dumps(match.qualification_data or {}, indent=2, ensure_ascii=False)}")
            print(f"  qualification_score = {match.qualification_score}")
            print(f"  status = {match.status.value}, sentiment = {match.sentiment.value}")

        print("\n" + "=" * 70)
        print("  PASO 3 — Diagnóstico: Antonio Torres (recomendación de carrera desalineada)")
        print("=" * 70)
        antonio = target_leads.get("Antonio Torres")
        if antonio is None:
            print("\n✗ No se pudo diagnosticar — lead de Antonio Torres no encontrado.")
            return 0

        conversations = (await db.execute(
            select(Conversation)
            .where(Conversation.lead_id == antonio.id)
            .order_by(Conversation.started_at)
        )).scalars().all()

        print(f"\nConversaciones encontradas para Antonio Torres: {len(conversations)}")
        for conv in conversations:
            messages = (await db.execute(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.created_at)
            )).scalars().all()
            print(f"\n--- Conversación {conv.id} (status={conv.status}, handler={conv.current_handler}, started_at={conv.started_at}) ---")
            for msg in messages:
                print(f"  [{msg.created_at}] {msg.role}: {msg.content}")

        print(f"\nlead.last_rag_context (Antonio Torres):")
        print(json.dumps(antonio.last_rag_context or {}, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
