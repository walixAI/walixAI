"""test_lead_dedup.py — Verificación del fix de leads duplicados por
teléfono (hallazgo 2026-08-25: 6 call-sites de creación de Lead usaban
hasta 4 formatos de teléfono distintos para el mismo número real).

Verificaciones:
  a) normalize_mx_phone produce el mismo resultado canónico para las 4
     variantes reales encontradas en el hallazgo (521.../52.../+52.../+521...)
     de un mismo número.
  b) Tras correr merge_duplicate_leads.py --confirm, no quedan grupos de
     leads duplicados por (tenant_id, teléfono normalizado) en TODA la BD
     (no solo Utel).
  c) find_lead_by_phone (bot_engine.py) encuentra un lead existente sin
     importar en cuál de los 4 formatos esté guardado su wa_phone.
  d) execute_tool("create_contact", ...) del Copilot detecta un teléfono
     ya existente (mismo número, formato distinto) y NO crea un duplicado.
  e) PASS/FAIL por cada verificación.

Este test NO borra los datos reales fusionados por merge_duplicate_leads.py
— corre después de esa fusión, sobre el estado ya limpio.

Uso:
    .venv/Scripts/python.exe scripts/test_lead_dedup.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.ai.bot_engine import find_lead_by_phone
from app.ai.copilot_tools import execute_tool
from app.core.database import AsyncSessionLocal
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole
from app.services.whatsapp import normalize_mx_phone

_NOPHONE_PREFIX = "NOPHONE_"


async def _setup_tenant() -> dict:
    async with AsyncSessionLocal() as db:
        tag = uuid.uuid4().hex[:8]
        tenant = Tenant(
            name=f"[test_lead_dedup] {tag}", email=f"leaddedup-{tag}@walix.test",
            plan=TenantPlan.STARTER, is_active=True,
        )
        db.add(tenant)
        await db.flush()
        company = Company(tenant_id=tenant.id, name="Empresa Test")
        db.add(company)
        await db.flush()
        branch = Branch(company_id=company.id, tenant_id=tenant.id, name="Sucursal", is_active=True)
        db.add(branch)
        await db.flush()
        owner = User(
            tenant_id=tenant.id, branch_id=branch.id, email=f"owner-{tag}@walix.test",
            name="Owner Test", hashed_password="not-used", role=UserRole.OWNER, is_active=True,
        )
        db.add(owner)
        await db.flush()
        await db.commit()
        return {"tenant": tenant, "branch": branch, "owner": owner}


async def _cleanup_tenant(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import delete
        await db.execute(delete(Tenant).where(Tenant.id == ctx["tenant"].id))
        await db.commit()


async def main() -> int:
    print("=" * 70)
    print("  test_lead_dedup.py — Fix de leads duplicados por teléfono")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []

    # ── a) normalize_mx_phone: mismo resultado para las 4 variantes reales ──
    variants = ["5215517278186", "+5215517278186", "525517278186", "+525517278186"]
    normalized = {normalize_mx_phone(v) for v in variants}
    ok_a = len(normalized) == 1 and next(iter(normalized)) == "525517278186"
    results.append((
        "a. normalize_mx_phone unifica las 4 variantes reales del hallazgo a un solo canónico",
        ok_a,
        f"variants={variants} normalized_set={normalized}",
    ))

    # ── b) sin grupos de duplicados en toda la BD ────────────────────────────
    async with AsyncSessionLocal() as db:
        all_leads = (await db.execute(select(Lead).where(Lead.deleted_at.is_(None)))).scalars().all()
        by_key: dict[tuple, list] = defaultdict(list)
        for lead in all_leads:
            if not lead.wa_phone or lead.wa_phone.startswith(_NOPHONE_PREFIX):
                continue
            canon = normalize_mx_phone(lead.wa_phone)
            if canon:
                by_key[(lead.tenant_id, canon)].append(lead.id)
        remaining_dups = {k: v for k, v in by_key.items() if len(v) > 1}
    ok_b = len(remaining_dups) == 0
    results.append((
        "b. Sin grupos de leads duplicados por teléfono en toda la BD (post-merge)",
        ok_b,
        f"grupos_restantes={len(remaining_dups)} detalle={dict(list(remaining_dups.items())[:5])}",
    ))

    # ── c) find_lead_by_phone encuentra sin importar el formato ─────────────
    ctx = await _setup_tenant()
    try:
        async with AsyncSessionLocal() as db:
            lead = Lead(
                branch_id=ctx["branch"].id, tenant_id=ctx["tenant"].id,
                wa_phone="525599990099", name="Formato Canónico",
                source=LeadSource.WHATSAPP_INBOUND, status=LeadStatus.NUEVO,
            )
            db.add(lead)
            await db.commit()
            await db.refresh(lead)

            found_variants = []
            for v in ["5215599990099", "+5215599990099", "+525599990099", "525599990099"]:
                found = await find_lead_by_phone(db, v, ctx["branch"].id, ctx["tenant"].id)
                found_variants.append(found is not None and found.id == lead.id)
        ok_c = all(found_variants)
        results.append((
            "c. find_lead_by_phone encuentra el mismo lead sin importar el formato del input",
            ok_c,
            f"encontrado_por_variante={found_variants}",
        ))

        # ── d) create_contact del Copilot detecta duplicado, no crea uno ────
        async with AsyncSessionLocal() as db:
            leads_before = (await db.execute(
                select(Lead).where(Lead.tenant_id == ctx["tenant"].id)
            )).scalars().all()
            count_before = len(leads_before)

            result = await execute_tool(
                "create_contact",
                {"name": "Formato Canónico (otra vez)", "wa_phone": "+52 55 9999 0099"},
                ctx["owner"], ctx["tenant"], db,
            )

            leads_after = (await db.execute(
                select(Lead).where(Lead.tenant_id == ctx["tenant"].id)
            )).scalars().all()
            count_after = len(leads_after)

        ok_d = "error" in result and count_after == count_before
        results.append((
            "d. Copilot create_contact detecta el duplicado (+52 con espacios) y no crea uno nuevo",
            ok_d,
            f"result={result} count_before={count_before} count_after={count_after}",
        ))
    finally:
        await _cleanup_tenant(ctx)

    return _report(results)


def _report(results: list[tuple[str, bool, str]]) -> int:
    print()
    all_ok = True
    for label, ok, detail in results:
        tag = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{tag}] {label}\n         {detail}")
    print()
    if all_ok:
        print("✓ Todas las verificaciones pasaron.")
        return 0
    print("✗ Al menos una verificación falló — ver detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
