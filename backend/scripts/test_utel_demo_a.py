"""test_utel_demo_a.py — Verificación de la demo Utel A (usuarios + prospectos
+ conversaciones), sembrada por scripts/admin/seed_utel_demo_a.py.

NO borra nada — Utel es un tenant real de cliente, la demo es borrable con
scripts/admin/purge_utel_demo_data.py cuando ya no se necesite, no acá.

Verificaciones:
  a) 160 leads con tag "Demo — Borrable", distribuidos en las 8 stages según
     lo especificado (números exactos, sin margen).
  b) Ningún usuario del tenant Utel (los 4 nuevos + el owner original) tiene
     wa_phone distinto de None — regression guard de seguridad explícito.
  c) Hay Conversations solo para leads en stage >= "profiling" — ninguna
     para leads en "new".
  d) Con set_tenant_context(db, tenant_utel.id), el aislamiento RLS es
     correcto: un SELECT de Lead sin filtro de tenant_id no ve leads de la
     clínica ni de ningún otro tenant (mismo patrón de detección de
     BYPASSRLS que test_tenant_utel.py, para no reportar un falso negativo
     si el rol de conexión de este entorno sigue bypasseando RLS).
  e) migrate... no aplica acá — en su lugar: correr
     purge_utel_demo_data.py en modo auditoría (sin --confirm) y confirmar
     que no borra nada.
  f) PASS/FAIL por cada verificación.

Uso:
    .venv/Scripts/python.exe scripts/test_utel_demo_a.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select, text

from app.core.database import AsyncSessionLocal, set_tenant_context
from app.models.conversation import Conversation
from app.models.lead import Lead
from app.models.pipeline import PipelineStage
from app.models.tag import Tag, lead_tags_table
from app.models.tenant import Tenant
from app.models.user import User

sys.path.insert(0, str(Path(__file__).resolve().parent / "admin"))
from purge_utel_demo_data import _audit_mode as _purge_audit_mode  # noqa: E402
from purge_utel_demo_data import _load_manifest  # noqa: E402

UTEL_EMAIL = "admin@utel.walix.mx"
REFERENCE_TENANT_EMAIL = "admin@clinica.com"
TAG_NAME = "Demo — Borrable"

EXPECTED_DISTRIBUTION = {
    "new": 40, "profiling": 30, "profiled": 25, "appointment": 20,
    "follow_up": 15, "docs": 12, "enrolled": 10, "lost": 8,
}


async def main() -> int:
    print("=" * 70)
    print("  test_utel_demo_a.py — Demo Utel A (usuarios + prospectos + conversaciones)")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.email == UTEL_EMAIL))).scalar_one_or_none()
        if tenant is None:
            print(f"\nNo existe el tenant Utel ({UTEL_EMAIL!r}).")
            return 1

        tag = (await db.execute(select(Tag).where(Tag.tenant_id == tenant.id, Tag.name == TAG_NAME))).scalar_one_or_none()
        if tag is None:
            print(f"\nNo existe el tag {TAG_NAME!r} para Utel — ¿se corrió seed_utel_demo_a.py?")
            return 1

        # ── a) 160 leads con el tag, distribuidos exacto por stage ──────────
        rows = (await db.execute(
            select(PipelineStage.stage_key, func.count(Lead.id))
            .select_from(lead_tags_table)
            .join(Lead, Lead.id == lead_tags_table.c.lead_id)
            .join(PipelineStage, PipelineStage.id == Lead.pipeline_stage_id)
            .where(lead_tags_table.c.tag_id == tag.id)
            .group_by(PipelineStage.stage_key)
        )).all()
        actual_distribution = dict(rows)
        total_tagged = sum(actual_distribution.values())
        ok_a = total_tagged == 160 and actual_distribution == EXPECTED_DISTRIBUTION
        results.append((
            "a. 160 leads con tag 'Demo — Borrable', distribuidos exacto en las 8 stages",
            ok_a,
            f"total={total_tagged} distribution={actual_distribution}",
        ))

        # ── b) ningún usuario de Utel tiene wa_phone ─────────────────────────
        users = (await db.execute(select(User).where(User.tenant_id == tenant.id))).scalars().all()
        offenders = [u.email for u in users if u.wa_phone is not None]
        ok_b = len(offenders) == 0
        results.append((
            "b. Ningún usuario del tenant Utel tiene wa_phone distinto de None",
            ok_b,
            f"usuarios_revisados={len(users)} con_wa_phone={offenders}",
        ))

        # ── c) Conversations solo para leads en stage >= 'profiling' ────────
        conv_stage_rows = (await db.execute(
            select(PipelineStage.stage_key, func.count(Conversation.id))
            .select_from(Conversation)
            .join(Lead, Lead.id == Conversation.lead_id)
            .join(PipelineStage, PipelineStage.id == Lead.pipeline_stage_id)
            .join(lead_tags_table, lead_tags_table.c.lead_id == Lead.id)
            .where(lead_tags_table.c.tag_id == tag.id)
            .group_by(PipelineStage.stage_key)
        )).all()
        conv_by_stage = dict(conv_stage_rows)
        ok_c = conv_by_stage.get("new", 0) == 0 and sum(conv_by_stage.values()) == 120
        results.append((
            "c. Conversations existen solo para stage != 'new' (ninguna para 'new')",
            ok_c,
            f"conversations_by_stage={conv_by_stage}",
        ))

        # ── d) aislamiento RLS (o detección de BYPASSRLS, sin falso negativo) ──
        reference_tenant = (await db.execute(
            select(Tenant).where(Tenant.email == REFERENCE_TENANT_EMAIL)
        )).scalar_one_or_none()

    async with AsyncSessionLocal() as db_rls:
        bypassrls = (await db_rls.execute(text(
            "SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ))).scalar_one_or_none()

        if bypassrls:
            policy_row = (await db_rls.execute(text(
                "SELECT qual FROM pg_policies WHERE tablename = 'leads' AND policyname = 'tenant_isolation_select'"
            ))).scalar_one_or_none()
            expected_qual = "(tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)"
            ok_d = policy_row == expected_qual
            detail_d = (
                f"current_user tiene BYPASSRLS=True en este entorno — un SELECT real no prueba "
                f"aislamiento acá (mismo hallazgo preexistente que test_tenant_utel.py). Se "
                f"verificó en su lugar que la policy tenant_isolation_select de leads tiene la "
                f"cláusula correcta: {'coincide' if ok_d else 'NO coincide'} (encontrado {policy_row!r})."
            )
        else:
            await set_tenant_context(db_rls, tenant.id)
            leads_from_utel_ctx = (await db_rls.execute(select(Lead))).scalars().all()
            other_tenant_ids = {l.tenant_id for l in leads_from_utel_ctx} - {tenant.id}
            ok_d = len(other_tenant_ids) == 0
            detail_d = f"leads_visibles={len(leads_from_utel_ctx)} tenant_ids_ajenos_vistos={other_tenant_ids}"

            if reference_tenant is not None:
                async with AsyncSessionLocal() as db_rls2:
                    await set_tenant_context(db_rls2, reference_tenant.id)
                    leads_from_ref_ctx = (await db_rls2.execute(select(Lead))).scalars().all()
                    leaked = [l for l in leads_from_ref_ctx if l.tenant_id == tenant.id]
                ok_d = ok_d and len(leaked) == 0
                detail_d += f" | desde contexto clínica: {len(leaked)} leads de Utel filtrados (debe ser 0)"

    results.append((
        "d. Aislamiento RLS (o verificación de policy si el rol de conexión tiene BYPASSRLS)",
        ok_d,
        detail_d,
    ))

    # ── e) purge en modo auditoría no borra nada ────────────────────────────
    try:
        manifest = _load_manifest()
    except SystemExit:
        results.append(("e. purge_utel_demo_data.py en modo auditoría no borra nada", False, "manifiesto no encontrado"))
        return _report(results)

    async def _snapshot() -> dict:
        async with AsyncSessionLocal() as db:
            tag_now = (await db.execute(select(Tag).where(Tag.tenant_id == tenant.id, Tag.name == TAG_NAME))).scalar_one_or_none()
            lead_count = (await db.execute(
                select(func.count()).select_from(lead_tags_table).where(lead_tags_table.c.tag_id == tag.id)
            )).scalar_one() if tag_now else 0
            return {"tag_exists": tag_now is not None, "tagged_lead_count": lead_count}

    before = await _snapshot()
    purge_exit_code = await _purge_audit_mode(manifest)
    after = await _snapshot()
    ok_e = before == after and purge_exit_code == 0
    results.append((
        "e. purge_utel_demo_data.py en modo auditoría (sin --confirm) no borra nada",
        ok_e,
        f"exit_code={purge_exit_code} before={before} after={after}",
    ))

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
