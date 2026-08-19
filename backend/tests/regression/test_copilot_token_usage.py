"""
Regresión — Copiloto Fase 1, Parte C: ai_token_usage (RLS estándar) +
fn_aggregate_token_usage_platform (agregación cross-tenant, migración
s4t5u6v7w8x9).

Mismo patrón que tests/regression/test_rls_5_tablas_pendientes.py: se
impersona walix_app vía SET LOCAL ROLE (impersonate_walix_app_or_skip) y se
llama la función SQL directo, nunca el wrapper Python.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_token_usage import AITokenUsage
from app.models.tenant import Tenant
from tests.regression.conftest import impersonate_walix_app_or_skip


async def test_ai_token_usage_isolated_by_rls(
    db: AsyncSession, tenant: Tenant, other_tenant_ctx: dict,
) -> None:
    own = AITokenUsage(
        tenant_id=tenant.id, source="copilot_chat", model_used="claude-haiku-4-5-20251001",
        input_tokens=100, output_tokens=50, estimated_cost_usd=Decimal("0.001234"),
    )
    other = AITokenUsage(
        tenant_id=other_tenant_ctx["tenant"].id, source="copilot_chat",
        model_used="claude-haiku-4-5-20251001",
        input_tokens=200, output_tokens=80, estimated_cost_usd=Decimal("0.002468"),
    )
    db.add_all([own, other])
    await db.flush()

    await impersonate_walix_app_or_skip(db)
    await db.execute(text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": str(tenant.id)})

    ids = {r[0] for r in (await db.execute(text("SELECT id FROM ai_token_usage"))).fetchall()}
    assert own.id in ids
    assert other.id not in ids


async def test_ai_token_usage_nullable_user_id_for_automated_sources(
    db: AsyncSession, tenant: Tenant,
) -> None:
    # source de un agente automático (Celery beat), sin user_id — no debe
    # fallar el insert ni la lectura bajo RLS.
    row = AITokenUsage(
        tenant_id=tenant.id, source="follow_up_agent", model_used="claude-sonnet-4-6",
        input_tokens=300, output_tokens=120, estimated_cost_usd=Decimal("0.005"),
        user_id=None,
    )
    db.add(row)
    await db.flush()

    await impersonate_walix_app_or_skip(db)
    await db.execute(text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": str(tenant.id)})

    found = (
        await db.execute(text("SELECT user_id FROM ai_token_usage WHERE id = :id"), {"id": row.id})
    ).scalar_one()
    assert found is None


async def test_fn_aggregate_token_usage_platform_sees_all_tenants_without_leaking_content(
    db: AsyncSession, tenant: Tenant, other_tenant_ctx: dict,
) -> None:
    now = datetime.now(timezone.utc)

    row_a = AITokenUsage(
        tenant_id=tenant.id, source="copilot_chat", model_used="claude-haiku-4-5-20251001",
        input_tokens=1000, output_tokens=400, estimated_cost_usd=Decimal("0.012000"),
    )
    row_b = AITokenUsage(
        tenant_id=other_tenant_ctx["tenant"].id, source="pipeline_agent", model_used="claude-sonnet-4-6",
        input_tokens=2000, output_tokens=900, estimated_cost_usd=Decimal("0.045000"),
    )
    db.add_all([row_a, row_b])
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    from_dt = now - timedelta(hours=1)
    to_dt = now + timedelta(hours=1)

    rows = {
        r.tenant_id: r
        for r in (
            await db.execute(
                text("SELECT * FROM fn_aggregate_token_usage_platform(:f, :t)"),
                {"f": from_dt, "t": to_dt},
            )
        ).fetchall()
    }

    assert rows[tenant.id].total_input_tokens == 1000
    assert rows[tenant.id].total_output_tokens == 400
    assert rows[tenant.id].tenant_name == tenant.name

    assert rows[other_tenant_ctx["tenant"].id].total_input_tokens == 2000
    assert rows[other_tenant_ctx["tenant"].id].total_output_tokens == 900

    # Solo agregados numéricos + tenant_name — ninguna columna de contenido
    # de conversación (source, model_used, id de fila individual, etc.)
    returned_columns = set(rows[tenant.id]._mapping.keys())
    assert returned_columns == {
        "tenant_id", "tenant_name", "total_input_tokens",
        "total_output_tokens", "total_cost_usd",
    }


async def test_fn_aggregate_token_usage_platform_respects_date_range(
    db: AsyncSession, tenant: Tenant,
) -> None:
    old_row = AITokenUsage(
        tenant_id=tenant.id, source="copilot_chat", model_used="claude-haiku-4-5-20251001",
        input_tokens=999, output_tokens=999, estimated_cost_usd=Decimal("1.0"),
    )
    db.add(old_row)
    await db.flush()
    # Empuja created_at fuera de rango sin depender de reloj real.
    await db.execute(
        text("UPDATE ai_token_usage SET created_at = :dt WHERE id = :id"),
        {"dt": datetime.now(timezone.utc) - timedelta(days=30), "id": old_row.id},
    )

    await impersonate_walix_app_or_skip(db)

    now = datetime.now(timezone.utc)
    rows = {
        r.tenant_id: r
        for r in (
            await db.execute(
                text("SELECT * FROM fn_aggregate_token_usage_platform(:f, :t)"),
                {"f": now - timedelta(hours=1), "t": now + timedelta(hours=1)},
            )
        ).fetchall()
    }
    assert tenant.id not in rows or rows[tenant.id].total_input_tokens == 0
