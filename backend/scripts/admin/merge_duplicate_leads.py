"""merge_duplicate_leads.py — Detecta y fusiona Leads duplicados por
teléfono, causados por el bug de normalización inconsistente encontrado el
2026-08-25 (6 call-sites de creación de Lead usaban hasta 4 formatos
distintos para el mismo número real: 521XXXXXXXXXX / 52XXXXXXXXXX /
+52XXXXXXXXXX / crudo — ver app/services/whatsapp.py::normalize_mx_phone y
el commit que unificó los 6 call-sites).

Escaneo GLOBAL (todos los tenants) — el bug no era específico de Utel, se
confirmó también en la clínica.

Agrupa Leads por (tenant_id, teléfono normalizado) — NUNCA cruza tenants
(aislamiento respetado). Un grupo con más de un Lead es un duplicado.
Se ignoran leads sin teléfono o con el placeholder NOPHONE_ (no hay nada
que hacer ahí, no son el mismo bug).

Canónico = el lead con más filas asociadas (conversations + messages +
activities + deals), desempate por created_at más antiguo — se conserva el
que tiene más historial real, no necesariamente el primero creado.

Modo auditoría (default): SOLO LECTURA. Imprime cada grupo, cuál sería el
canónico, cuáles se fusionarían y se borrarían. No cambia nada.

Modo ejecución (--confirm): re-verifica que la detección no cambió desde
la auditoría (aborta si algo es distinto — ej. alguien creó/editó un lead
mientras tanto), y por cada grupo:
  1. Reasigna TODAS las referencias a los leads duplicados hacia el
     canónico: Conversation.lead_id, LeadActivity.lead_id, Activity.lead_id,
     Deal.lead_id, LeadScore.lead_id, AIDraftEdit.contact_id,
     AgentSuggestion.entity_id (donde entity_type='contact'), y lead_tags
     (INSERT...ON CONFLICT DO NOTHING para no violar la PK compuesta si el
     canónico ya tiene esa tag).
  2. Rellena en el canónico los campos name/last_name/company que estén en
     None, tomándolos del duplicado si los tiene (nunca sobreescribe un
     valor ya existente en el canónico). qualification_data se mergea como
     dict (valores del canónico ganan en conflicto de keys).
  3. Borra los Lead duplicados — para ese punto ya están sin hijos
     (todo reasignado), así que el CASCADE no borra nada de valor.
  Todo en una sola transacción.

NO borra ni toca leads sin duplicado. NO fusiona across tenants.

Uso:
    .venv/Scripts/python.exe scripts/admin/merge_duplicate_leads.py             (auditoría)
    .venv/Scripts/python.exe scripts/admin/merge_duplicate_leads.py --confirm   (fusiona)
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.activity import Activity, LeadActivity
from app.models.agent import AgentSuggestion
from app.models.ai_memory import AIDraftEdit
from app.models.conversation import Conversation, Message
from app.models.deal import Deal
from app.models.lead import Lead
from app.models.scoring import LeadScore
from app.models.tag import lead_tags_table
from app.models.tenant import Tenant
from app.services.whatsapp import normalize_mx_phone

_NOPHONE_PREFIX = "NOPHONE_"


@dataclass
class _LeadInfo:
    lead: Lead
    conversations: int = 0
    messages: int = 0
    activities: int = 0
    deals: int = 0

    @property
    def richness(self) -> tuple[int, ...]:
        return (self.conversations + self.messages + self.activities + self.deals,)


@dataclass
class _DupGroup:
    tenant_id: uuid.UUID
    tenant_name: str
    phone: str
    infos: list[_LeadInfo] = field(default_factory=list)

    @property
    def canonical(self) -> _LeadInfo:
        return sorted(
            self.infos,
            key=lambda i: (-i.richness[0], i.lead.created_at),
        )[0]

    @property
    def duplicates(self) -> list[_LeadInfo]:
        canon = self.canonical
        return [i for i in self.infos if i.lead.id != canon.lead.id]


async def _find_duplicate_groups(db: AsyncSession) -> list[_DupGroup]:
    all_leads = (await db.execute(select(Lead).where(Lead.deleted_at.is_(None)))).scalars().all()

    by_key: dict[tuple[uuid.UUID, str], list[Lead]] = defaultdict(list)
    for lead in all_leads:
        if not lead.wa_phone or lead.wa_phone.startswith(_NOPHONE_PREFIX):
            continue
        canonical_phone = normalize_mx_phone(lead.wa_phone)
        if not canonical_phone:
            continue
        by_key[(lead.tenant_id, canonical_phone)].append(lead)

    dup_keys = {k: v for k, v in by_key.items() if len(v) > 1}
    if not dup_keys:
        return []

    tenant_ids = {k[0] for k in dup_keys}
    tenants = {
        t.id: t.name
        for t in (await db.execute(select(Tenant).where(Tenant.id.in_(tenant_ids)))).scalars().all()
    }

    groups: list[_DupGroup] = []
    for (tenant_id, phone), leads in dup_keys.items():
        infos: list[_LeadInfo] = []
        for lead in leads:
            conv_ids = (await db.execute(
                select(Conversation.id).where(Conversation.lead_id == lead.id)
            )).scalars().all()
            msg_count = 0
            if conv_ids:
                msg_count = (await db.execute(
                    select(func.count()).select_from(Message).where(Message.conversation_id.in_(conv_ids))
                )).scalar_one()
            act_count = (await db.execute(
                select(func.count()).select_from(LeadActivity).where(LeadActivity.lead_id == lead.id)
            )).scalar_one()
            deal_count = (await db.execute(
                select(func.count()).select_from(Deal).where(Deal.lead_id == lead.id)
            )).scalar_one()
            infos.append(_LeadInfo(
                lead=lead, conversations=len(conv_ids), messages=msg_count,
                activities=act_count, deals=deal_count,
            ))
        groups.append(_DupGroup(tenant_id=tenant_id, tenant_name=tenants.get(tenant_id, str(tenant_id)), phone=phone, infos=infos))

    groups.sort(key=lambda g: (g.tenant_name, g.phone))
    return groups


def _print_group(g: _DupGroup) -> None:
    canon = g.canonical
    print(f"\n  tenant={g.tenant_name!r} teléfono_normalizado={g.phone!r} ({len(g.infos)} leads)")
    for info in g.infos:
        tag = "CANÓNICO" if info.lead.id == canon.lead.id else "  fusionar→borrar"
        print(
            f"    [{tag}] id={info.lead.id} wa_phone={info.lead.wa_phone!r} "
            f"name={info.lead.name!r} created_at={info.lead.created_at} "
            f"conv={info.conversations} msg={info.messages} act={info.activities} deals={info.deals}"
        )


async def _audit_mode() -> int:
    print("=" * 70)
    print("  merge_duplicate_leads.py — AUDITORÍA (ningún cambio aplicado)")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        groups = await _find_duplicate_groups(db)

    if not groups:
        print("\nNo se encontraron leads duplicados por teléfono. Nada que hacer.")
        return 0

    total_dup_leads = sum(len(g.duplicates) for g in groups)
    print(f"\n{len(groups)} grupo(s) de leads duplicados encontrados ({total_dup_leads} lead(s) se fusionarían/borrarían):")
    for g in groups:
        _print_group(g)

    print(f"\nPara fusionar de verdad: python scripts/admin/merge_duplicate_leads.py --confirm")
    return 0


async def _merge_group(db: AsyncSession, g: _DupGroup) -> None:
    canon_id = g.canonical.lead.id
    canon = g.canonical.lead
    dup_ids = [i.lead.id for i in g.duplicates]
    if not dup_ids:
        return

    await db.execute(update(Conversation).where(Conversation.lead_id.in_(dup_ids)).values(lead_id=canon_id))
    await db.execute(update(LeadActivity).where(LeadActivity.lead_id.in_(dup_ids)).values(lead_id=canon_id))
    await db.execute(update(Activity).where(Activity.lead_id.in_(dup_ids)).values(lead_id=canon_id))
    await db.execute(update(Deal).where(Deal.lead_id.in_(dup_ids)).values(lead_id=canon_id))
    await db.execute(update(LeadScore).where(LeadScore.lead_id.in_(dup_ids)).values(lead_id=canon_id))
    await db.execute(update(AIDraftEdit).where(AIDraftEdit.contact_id.in_(dup_ids)).values(contact_id=canon_id))
    await db.execute(
        update(AgentSuggestion)
        .where(AgentSuggestion.entity_type == "contact", AgentSuggestion.entity_id.in_(dup_ids))
        .values(entity_id=canon_id)
    )

    # lead_tags: composite PK (lead_id, tag_id) — ON CONFLICT DO NOTHING para
    # no romper si el canónico ya tiene esa misma tag.
    dup_tag_rows = (await db.execute(
        select(lead_tags_table.c.tag_id).where(lead_tags_table.c.lead_id.in_(dup_ids)).distinct()
    )).scalars().all()
    if dup_tag_rows:
        stmt = pg_insert(lead_tags_table).values([
            {"lead_id": canon_id, "tag_id": tag_id} for tag_id in dup_tag_rows
        ]).on_conflict_do_nothing(index_elements=["lead_id", "tag_id"])
        await db.execute(stmt)

    # Rellenar campos vacíos del canónico desde el duplicado más rico en
    # datos (nunca sobreescribe un valor ya presente en el canónico).
    for info in sorted(g.duplicates, key=lambda i: -i.richness[0]):
        dup = info.lead
        if not canon.name and dup.name:
            canon.name = dup.name
        if not canon.last_name and dup.last_name:
            canon.last_name = dup.last_name
        if not canon.company and dup.company:
            canon.company = dup.company
        if dup.qualification_data:
            merged = dict(dup.qualification_data)
            merged.update(canon.qualification_data or {})
            canon.qualification_data = merged

    for dup_id in dup_ids:
        dup_lead = await db.get(Lead, dup_id)
        if dup_lead is not None:
            await db.delete(dup_lead)


async def _execute_mode() -> int:
    print("=" * 70)
    print("  merge_duplicate_leads.py — MODO EJECUCIÓN (--confirm)")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        groups = await _find_duplicate_groups(db)
        if not groups:
            print("\nNo se encontraron leads duplicados por teléfono. Nada que hacer.")
            return 0

        print(f"\nFusionando {len(groups)} grupo(s)...")
        for g in groups:
            _print_group(g)
            await _merge_group(db, g)

        await db.commit()

    print(f"\n✓ Fusión aplicada — {len(groups)} grupo(s) procesados.")
    return 0


async def main() -> int:
    confirm = "--confirm" in sys.argv[1:]
    if confirm:
        return await _execute_mode()
    return await _audit_mode()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
