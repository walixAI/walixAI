"""
Regresión — Multi-tenancy: aislamiento a nivel aplicación + verificación de RLS.

Código auditado:
  - app/api/deals.py (_get_deal_or_404 filtra por tenant_id)
  - app/api/dashboard_widgets.py (delete_panel filtra por tenant_id)
  - alembic/versions/h4i5j6k7l8m9_add_row_level_security.py (_DIRECT_TABLES:
    leads, users, branches, knowledge_documents, knowledge_chunks,
    lead_activities, agent_suggestions, lead_scores, daily_metrics,
    sentiment_snapshots, pipeline_stages, onboarding_drafts,
    meta_lead_configs, activities, tags, ai_command_logs, alert_rules,
    support_sessions + policies manuales para conversations/messages/lead_tags).
  - alembic/versions/s6t7u8v9w0x1_sprint13a_deals.py y
    t7u8v9w0x1y2_sprint14a_deal_fields_and_history.py — `deals` y
    `deal_stage_history` tienen RLS desde su creación (2026-06-19, posterior
    a h4i5j6k7l8m9), con el mismo patrón tenant_isolation_*. NO les faltaba
    RLS — un audit anterior de este módulo lo afirmaba incorrectamente.
  - alembic/versions/k6l7m8n9o0p1_rls_dashboard_panels.py — `dashboard_panels`
    SÍ era el gap real (creada en e40231c281ca, sin RLS hasta esta migración).
  - app/core/database.py — get_db hace `set_config('app.current_tenant_id', ...)`
    por request; las policies de RLS comparan contra ese valor.

── HALLAZGO DE INFRAESTRUCTURA (histórico, ya mitigado en los tests de este
   módulo — ver "Cómo se prueba RLS de verdad" más abajo) ────────────────────
El rol de Postgres que usa hoy la aplicación en Railway (`postgres`, el
default) tiene `rolsuper=TRUE` y `rolbypassrls=TRUE`:

    SELECT current_user, rolsuper, rolbypassrls FROM pg_roles
    WHERE rolname = current_user;
    -- postgres | true | true

Un superusuario de Postgres ignora RLS incluso con FORCE ROW LEVEL SECURITY
(FORCE solo remueve el bypass del DUEÑO de la tabla, no el de un superusuario
real). Mientras la app runtime se siga conectando como `postgres` en
producción, el aislamiento multi-tenant depende ahí 100% del filtro
`WHERE tenant_id = ...` a nivel de aplicación — RLS es una segunda línea de
defensa real solo una vez que Railway repunte `DATABASE_URL` al rol
`walix_app` (sin bypass), creado vía `scripts/setup_db_user.py`. Ese cutover
de `DATABASE_URL` en cada entorno lo hace Walix a mano, coordinado — no es
parte de este cambio de código (ver notas en scripts/setup_db_user.py y
app/core/config.py: Settings.effective_alembic_database_url).

── CÓMO SE PRUEBA RLS DE VERDAD SIN ESE CUTOVER ──────────────────────────────
Los tests de este módulo corren con la conexión admin compartida de toda la
suite (`db`, fixture de tests/sprint7/conftest.py) porque CADA OTRO fixture
de esta suite (tenant/branch/lead/etc. en decenas de archivos) depende de
insertar sin restricciones de RLS. Si el `DATABASE_URL` de test se repuntara
a `walix_app` directamente, esos fixtures romperían en cadena: ninguno llama
`set_config('app.current_tenant_id', ...)` antes de insertar (esa
responsabilidad hoy vive solo en `get_db()`, para requests HTTP reales) — un
INSERT en una tabla con RLS sin ese contexto seteado es rechazado por la
policy (WITH CHECK evalúa contra NULL). Repuntar el DATABASE_URL de test
completo está fuera de alcance de este cambio (ver resumen del prompt).

En su lugar, los tres tests de bypass de abajo usan `SET LOCAL ROLE
walix_app` DENTRO de la misma transacción/conexión admin ya abierta por el
fixture `db`: como la conexión es un superusuario, puede impersonar
cualquier rol sin necesitar su contraseña, y Postgres evalúa RLS según el
rol efectivo de la sesión (no el rol de login) — así que las queries que
corren DESPUÉS del SET ROLE quedan genuinamente sujetas a las mismas
policies que tendría una conexión real como walix_app. `SET LOCAL` es
transaccional: se revierte solo al hacer ROLLBACK TO SAVEPOINT en el
teardown del fixture, sin filtrar entre tests. Si el rol `walix_app` todavía
no existe en este entorno (Walix no corrió el SQL de
`scripts/setup_db_user.py` todavía), el test se salta con un mensaje claro
en vez de fallar. El helper vive en conftest.py
(`impersonate_walix_app_or_skip`) — compartido con
tests/regression/test_pretenant_lookups.py (login/check-email/webhook, que
además dependen de las funciones SECURITY DEFINER de la migración
l7m8n9o0p1q2 para resolver el tenant antes de conocerlo).

`scripts/test_rls_role.py` es el complemento de esto: un script standalone
que sí abre una conexión REAL como walix_app (con su password real, nunca
hardcodeada) para validar que las credenciales/permisos end-to-end funcionan
una vez que Walix termine el setup — ese es el momento en que se prueba la
conexión de verdad, no en esta suite de pytest.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_layout import DashboardPanel
from app.models.deal import Deal
from app.models.pipeline import PipelineStage
from app.models.pipeline_group import Pipeline
from tests.regression.conftest import impersonate_walix_app_or_skip as _impersonate_walix_app_or_skip


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
# Los tres tests de abajo siguen el mismo patrón: crean una fila para el
# tenant B (other_tenant_ctx) con la conexión admin normal, se paran como el
# tenant A vía set_config, impersonan walix_app vía SET LOCAL ROLE, y corren
# una query RAW deliberadamente SIN WHERE tenant_id — dejando que sea RLS (no
# el filtro de aplicación) quien tenga que bloquear el acceso.

async def test_rls_bypass_leaks_cross_tenant_lead_when_querying_unfiltered(
    db: AsyncSession, tenant, contact, other_tenant_ctx: dict,
) -> None:
    """`leads` está en _DIRECT_TABLES desde h4i5j6k7l8m9. Con
    app.current_tenant_id apuntando al tenant A y la sesión impersonando
    walix_app (sin bypass), una query RAW sin WHERE tenant_id sobre un lead
    del tenant B NO debe devolver filas — y ahora sí lo verificamos contra un
    rol real sin BYPASSRLS, no solo documentamos que fallaría.
    """
    other_lead_id = uuid.uuid4()
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

    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, FALSE)"),
        {"tid": str(tenant.id)},
    )
    await _impersonate_walix_app_or_skip(db)

    leaked = (
        await db.execute(text("SELECT id FROM leads WHERE id = :lid"), {"lid": str(other_lead_id)})
    ).scalar_one_or_none()

    assert leaked is None, (
        "RLS no bloqueó el acceso cruzado al saltarse el filtro de aplicación, "
        "incluso impersonando walix_app (sin BYPASSRLS) — revisar las policies "
        "de la migración h4i5j6k7l8m9 para la tabla leads."
    )


async def test_rls_bypass_leaks_cross_tenant_deal_when_querying_unfiltered(
    db: AsyncSession, tenant, other_tenant_ctx: dict,
) -> None:
    """`deals` tiene RLS desde su creación (s6t7u8v9w0x1_sprint13a_deals) —
    verificado con pg_class.relrowsecurity antes de escribir este test, no
    asumido. Mismo patrón que el test de leads, pero para deals."""
    from app.models.lead import Lead, LeadStatus

    other_lead = Lead(
        branch_id=other_tenant_ctx["branch"].id,
        tenant_id=other_tenant_ctx["tenant"].id,
        wa_phone="+5215500000098",
        name="Lead para Deal Tenant B",
        status=LeadStatus.NUEVO,
    )
    db.add(other_lead)
    await db.flush()

    other_pipeline = Pipeline(
        tenant_id=other_tenant_ctx["tenant"].id,
        branch_id=other_tenant_ctx["branch"].id,
        name="Pipeline Tenant B",
        is_default=True,
        position=0,
    )
    db.add(other_pipeline)
    await db.flush()

    other_stage = PipelineStage(
        tenant_id=other_tenant_ctx["tenant"].id,
        branch_id=other_tenant_ctx["branch"].id,
        pipeline_id=other_pipeline.id,
        name="Nuevo",
        slug="nuevo",
        order_index=0,
    )
    db.add(other_stage)
    await db.flush()

    other_deal_id = uuid.uuid4()
    other_deal = Deal(
        id=other_deal_id,
        tenant_id=other_tenant_ctx["tenant"].id,
        lead_id=other_lead.id,
        pipeline_stage_id=other_stage.id,
        title="Deal Tenant B",
        amount=5000,
    )
    db.add(other_deal)
    await db.flush()

    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, FALSE)"),
        {"tid": str(tenant.id)},
    )
    await _impersonate_walix_app_or_skip(db)

    leaked = (
        await db.execute(text("SELECT id FROM deals WHERE id = :did"), {"did": str(other_deal_id)})
    ).scalar_one_or_none()

    assert leaked is None, (
        "RLS no bloqueó el acceso cruzado a deals al saltarse el filtro de "
        "aplicación, incluso impersonando walix_app (sin BYPASSRLS)."
    )


async def test_rls_bypass_leaks_cross_tenant_dashboard_panel_when_querying_unfiltered(
    db: AsyncSession, tenant, other_tenant_ctx: dict,
) -> None:
    """`dashboard_panels` era el gap real (sin RLS hasta la migración
    k6l7m8n9o0p1_rls_dashboard_panels). Mismo patrón de verificación."""
    other_panel_id = uuid.uuid4()
    other_panel = DashboardPanel(
        id=other_panel_id,
        tenant_id=other_tenant_ctx["tenant"].id,
        key="panel-tenant-b",
        name="Panel Tenant B",
        is_system=False,
        position=0,
        created_by=other_tenant_ctx["user"].id,
    )
    db.add(other_panel)
    await db.flush()

    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, FALSE)"),
        {"tid": str(tenant.id)},
    )
    await _impersonate_walix_app_or_skip(db)

    leaked = (
        await db.execute(
            text("SELECT id FROM dashboard_panels WHERE id = :pid"), {"pid": str(other_panel_id)}
        )
    ).scalar_one_or_none()

    assert leaked is None, (
        "RLS no bloqueó el acceso cruzado a dashboard_panels al saltarse el "
        "filtro de aplicación, incluso impersonando walix_app (sin BYPASSRLS)."
    )
