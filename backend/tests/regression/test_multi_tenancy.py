"""
Regresión — Multi-tenancy: aislamiento a nivel aplicación + verificación de RLS.

Código auditado:
  - app/api/deals.py (_get_deal_or_404 filtra por tenant_id)
  - app/api/dashboard_widgets.py (delete_panel filtra por tenant_id)
  - alembic/versions/h4i5j6k7l8m9_add_row_level_security.py (lista real de
    tablas con RLS: _DIRECT_TABLES = ["leads", "users", "branches",
    "knowledge_documents", "knowledge_chunks", "lead_activities",
    "agent_suggestions", "lead_scores", "daily_metrics", "sentiment_snapshots",
    "pipeline_stages", "onboarding_drafts", "meta_lead_configs", "activities",
    "tags", "ai_command_logs", "alert_rules", "support_sessions"] + policies
    manuales para conversations/messages/lead_tags. `deals`,
    `deal_stage_history` y `dashboard_panels` NO están en esa lista — se
    crearon en migraciones posteriores (Sprint 13/consolidación dashboard) y
    la migración de RLS nunca se actualizó para cubrirlas.
  - app/core/database.py — get_db hace `set_config('app.current_tenant_id', ...)`
    por request; las policies de RLS comparan contra ese valor.

── HALLAZGO CRÍTICO DE ESTA AUDITORÍA (no relacionado con el código de la app,
   sino con la configuración de infraestructura) ──────────────────────────────
El rol de Postgres que usa la aplicación (`postgres`, el default de Railway)
tiene `rolsuper=TRUE` y `rolbypassrls=TRUE` — verificado directamente:

    SELECT current_user, rolsuper, rolbypassrls FROM pg_roles
    WHERE rolname = current_user;
    -- postgres | true | true

Esto significa que **todas las políticas de RLS creadas por la migración
h4i5j6k7l8m9 son inertes en este entorno**: un superusuario de Postgres
ignora RLS incluso con FORCE ROW LEVEL SECURITY (FORCE solo remueve el bypass
del dueño de la tabla, no el de un superusuario real). El aislamiento
multi-tenant depende HOY 100% del filtro `WHERE tenant_id = ...` a nivel de
aplicación — RLS no es una segunda línea de defensa real mientras la app siga
conectándose como `postgres`.

`test_rls_bypass_leaks_cross_tenant_lead_when_querying_unfiltered` prueba
esto de forma determinística y se espera que FALLE en este entorno — no es
flaky, es el comportamiento real de la infraestructura actual. No se corrige
aquí (fuera de alcance de esta suite: requeriría crear un rol de aplicación
sin bypass de RLS, p. ej. `walix_app`, y migrar `DATABASE_URL`); se deja
documentado como FAIL en el resumen de la suite, tal como lo pide el alcance
quirúrgico de este prompt.
"""
from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_layout import DashboardPanel
from app.models.deal import Deal
from app.models.pipeline import PipelineStage


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── § 1: Aislamiento a nivel aplicación (Deal / DashboardPanel) ──────────────

async def test_cannot_read_other_tenant_deal(
    client: AsyncClient, deal: Deal, other_tenant_ctx: dict,
) -> None:
    r = await client.get(f"/api/deals/{deal.id}", headers=auth(other_tenant_ctx["token"]))
    assert r.status_code == 404


async def test_cannot_update_other_tenant_deal(
    client: AsyncClient, deal: Deal, owner_token: str, other_tenant_ctx: dict,
) -> None:
    r = await client.patch(
        f"/api/deals/{deal.id}", json={"title": "Hackeado"},
        headers=auth(other_tenant_ctx["token"]),
    )
    assert r.status_code == 404

    check = await client.get(f"/api/deals/{deal.id}", headers=auth(owner_token))
    assert check.json()["title"] != "Hackeado"


async def test_cannot_delete_other_tenant_deal(
    client: AsyncClient, deal: Deal, other_tenant_ctx: dict,
) -> None:
    r = await client.delete(f"/api/deals/{deal.id}", headers=auth(other_tenant_ctx["token"]))
    assert r.status_code == 404


async def test_deals_list_only_returns_own_tenant(
    client: AsyncClient, db: AsyncSession, tenant, contact, stages: list[PipelineStage],
    owner_token: str, other_tenant_ctx: dict, owner_user,
) -> None:
    mine = Deal(
        tenant_id=tenant.id, lead_id=contact.id, pipeline_stage_id=stages[0].id,
        title="Mío", amount=1000, owner_id=owner_user.id,
    )
    db.add(mine)
    await db.flush()

    r = await client.get("/api/deals", headers=auth(other_tenant_ctx["token"]))
    assert r.status_code == 200, r.text
    ids = {item["id"] for item in r.json()["items"]}
    assert str(mine.id) not in ids


async def test_cannot_delete_other_tenant_dashboard_panel(
    client: AsyncClient, db: AsyncSession, tenant, owner_user, other_tenant_ctx: dict,
) -> None:
    panel = DashboardPanel(
        tenant_id=tenant.id, key="panel-propio", name="Panel Propio",
        is_system=False, position=0, created_by=owner_user.id,
    )
    db.add(panel)
    await db.flush()

    r = await client.delete(
        f"/api/dashboard/panels/{panel.id}", headers=auth(other_tenant_ctx["token"])
    )
    assert r.status_code == 404


# ── § 2: RLS — bypass del filtro de aplicación ────────────────────────────────

async def test_rls_bypass_leaks_cross_tenant_lead_when_querying_unfiltered(
    db: AsyncSession, tenant, contact, other_tenant_ctx: dict,
) -> None:
    """`leads` SÍ está en la lista de RLS (_DIRECT_TABLES). Con
    app.current_tenant_id apuntando al tenant A, una query RAW sin WHERE
    tenant_id sobre un lead del tenant B NO debería devolver filas.

    Se espera que este test FALLE en el entorno actual — ver docstring del
    módulo. Documentado como hallazgo real, no se debilita la aserción para
    hacerlo pasar artificialmente.
    """
    other_lead_id = uuid.uuid4()
    # Insertamos un lead mínimo para el tenant B usando SQL crudo con
    # RETURNING, ya que no tenemos el fixture `contact` para other_tenant_ctx.
    from app.models.lead import Lead, LeadStatus

    other_lead = Lead(
        id=other_lead_id,
        branch_id=other_tenant_ctx["branch"].id,
        tenant_id=other_tenant_ctx["tenant"].id,
        wa_phone="+5215500000099",
        name="Lead Tenant B",
        status=LeadStatus.NUEVO,
    )
    db.add(other_lead)
    await db.flush()

    # Contexto RLS: nos "sentamos" como el tenant A (dueño de `contact`).
    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, FALSE)"),
        {"tid": str(tenant.id)},
    )

    # Query RAW, deliberadamente SIN WHERE tenant_id — saltándose el filtro
    # de aplicación para dejar que sea RLS quien bloquee (o no) el acceso.
    leaked = (
        await db.execute(text("SELECT id FROM leads WHERE id = :lid"), {"lid": str(other_lead_id)})
    ).scalar_one_or_none()

    assert leaked is None, (
        "RLS no bloqueó el acceso cruzado al saltarse el filtro de aplicación — "
        "ver hallazgo documentado en el docstring de este módulo: el rol de "
        "conexión de la app (postgres) tiene rolbypassrls=TRUE, por lo que "
        "TODAS las políticas de RLS son inertes en este entorno."
    )


async def test_rls_not_defined_for_deals_table(db: AsyncSession) -> None:
    """`deals` no aparece en _DIRECT_TABLES de la migración de RLS — se
    documenta como pendiente en vez de fallar una aserción de seguridad que
    nunca se implementó.

    TODO: activar un test real de bypass para `deals` cuando se agregue una
    migración de RLS específica para esta tabla (y para deal_stage_history).
    """
    has_rls = (
        await db.execute(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = 'deals'")
        )
    ).scalar_one_or_none()
    if not has_rls:
        import pytest
        pytest.skip(
            "RLS no está habilitado para la tabla 'deals' todavía — "
            "TODO: activar cuando se agregue la migración correspondiente."
        )


async def test_rls_not_defined_for_dashboard_panels_table(db: AsyncSession) -> None:
    """Igual que arriba, para `dashboard_panels`.

    TODO: activar cuando se agregue la migración de RLS para dashboard_panels.
    """
    has_rls = (
        await db.execute(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = 'dashboard_panels'")
        )
    ).scalar_one_or_none()
    if not has_rls:
        import pytest
        pytest.skip(
            "RLS no está habilitado para la tabla 'dashboard_panels' todavía — "
            "TODO: activar cuando se agregue la migración correspondiente."
        )
