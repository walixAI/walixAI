"""
Regresión — Dashboard: paneles múltiples (consolidación reciente).

Código auditado: app/api/dashboard_widgets.py, app/models/dashboard_layout.py,
alembic/versions/e40231c281ca_dashboard_panels_schema.py (seed real de paneles
del sistema: key="principal" min_role=None, key="desempeno" min_role="owner").

Notas de auditoría:
  - GET /api/dashboard/panels FILTRA en silencio los paneles a los que el
    usuario no tiene acceso (no devuelve 403) — `_user_can_see_panel` se usa
    como predicado de una list-comprehension en `list_panels`. Un usuario
    no-owner simplemente no ve "Desempeño" en la lista.
  - GET /api/dashboard/widgets-catalog?panel=desempeno para un usuario
    no-owner SÍ devuelve 403 — ahí `_get_panel_or_404` levanta la excepción
    directamente. Backend gatea en los dos endpoints, pero con
    comportamientos distintos (filtrado vs 403); ambos se cubren aquí tal
    como existen.
  - Catálogo de widgets: paneles `is_system=True` filtran por
    `DashboardWidget.surface == panel.key` (exacto). Paneles `is_system=False`
    (custom) devuelven TODOS los widgets activos, sin filtrar por surface —
    este fue el bug corregido en el Prompt 5 de la consolidación
    (`_get_active_visible_widgets`, dashboard_widgets.py:161-176). Se cubre
    explícitamente como regresión con nombre de test que referencia el bug.
  - GET /reports → redirect a /dashboard?panel=desempeno es una ruta 100%
    de frontend (React Router `<Navigate>` en frontend/src/App.tsx:100) — el
    backend no tiene endpoint `/reports`. Cubierto en
    e2e/regression/dashboard_panels.spec.ts, no aquí.
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_layout import DashboardPanel, DashboardWidget
from app.models.tenant import Tenant
from app.models.user import User


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture()
async def system_panels(db: AsyncSession, tenant: Tenant) -> dict[str, DashboardPanel]:
    """Recrea los 2 paneles del sistema tal como los siembra la migración e40231c281ca."""
    principal = DashboardPanel(
        tenant_id=tenant.id, key="principal", name="Principal",
        min_role=None, is_system=True, position=0, created_by=None,
    )
    desempeno = DashboardPanel(
        tenant_id=tenant.id, key="desempeno", name="Desempeño",
        min_role="owner", is_system=True, position=1, created_by=None,
    )
    db.add_all([principal, desempeno])
    await db.flush()
    return {"principal": principal, "desempeno": desempeno}


@pytest_asyncio.fixture()
async def widgets_multi_surface(db: AsyncSession) -> dict[str, DashboardWidget]:
    """3 widgets activos con surfaces distintos, para probar el filtro por surface."""
    suffix = uuid.uuid4().hex[:8]
    principal_w = DashboardWidget(
        key=f"w-principal-{suffix}", name="Widget Principal", native_key="native.principal",
        is_active=True, is_mandatory=False, default_position=0, surface="principal",
    )
    desempeno_w = DashboardWidget(
        key=f"w-desempeno-{suffix}", name="Widget Desempeño", native_key="native.desempeno",
        is_active=True, is_mandatory=False, default_position=0, surface="desempeno",
    )
    other_w = DashboardWidget(
        key=f"w-other-{suffix}", name="Widget Otro", native_key="native.other",
        is_active=True, is_mandatory=False, default_position=0, surface="otra_superficie",
    )
    db.add_all([principal_w, desempeno_w, other_w])
    await db.flush()
    return {"principal": principal_w, "desempeno": desempeno_w, "other": other_w}


# ── Listado de paneles — aislamiento por usuario ──────────────────────────────

async def test_list_panels_includes_system_panels(
    client: AsyncClient, system_panels: dict, owner_token: str,
) -> None:
    r = await client.get("/api/dashboard/panels", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    keys = {p["key"] for p in r.json()}
    assert {"principal", "desempeno"}.issubset(keys)


async def test_list_panels_excludes_desempeno_for_non_owner(
    client: AsyncClient, system_panels: dict, asesor_token: str,
) -> None:
    """Un asesor no ve el panel 'desempeno' (min_role=owner) en el listado — filtrado, no 403."""
    r = await client.get("/api/dashboard/panels", headers=auth(asesor_token))
    assert r.status_code == 200, r.text
    keys = {p["key"] for p in r.json()}
    assert "principal" in keys
    assert "desempeno" not in keys


async def test_list_panels_never_shows_custom_panel_of_another_user(
    client: AsyncClient, db: AsyncSession, tenant: Tenant,
    owner_user: User, owner_token: str, manager_token: str, asesor_token: str,
) -> None:
    """Un panel custom de OTRO usuario nunca aparece — ni siquiera para owner/IT."""
    foreign_panel = DashboardPanel(
        tenant_id=tenant.id, key="panel-ajeno", name="Panel Ajeno",
        is_system=False, position=5, created_by=owner_user.id,
    )
    db.add(foreign_panel)
    await db.flush()

    for token in (manager_token, asesor_token):
        r = await client.get("/api/dashboard/panels", headers=auth(token))
        assert r.status_code == 200, r.text
        keys = {p["key"] for p in r.json()}
        assert "panel-ajeno" not in keys, (
            "Un panel custom ajeno se filtró incorrectamente hacia otro usuario del tenant"
        )


# ── Creación de panel custom ──────────────────────────────────────────────────

async def test_create_panel_associates_to_creator(
    client: AsyncClient, owner_token: str, owner_user: User,
) -> None:
    r = await client.post(
        "/api/dashboard/panels",
        json={"name": "Mi Panel de Ventas"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created_by"] == str(owner_user.id)
    assert body["is_system"] is False
    assert body["key"]  # slug no vacío


# ── Borrado de panel custom — solo el creador ─────────────────────────────────

async def test_delete_custom_panel_forbidden_for_non_creator(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, owner_user: User,
    owner_token: str, manager_token: str,
) -> None:
    panel = DashboardPanel(
        tenant_id=tenant.id, key="panel-del-owner", name="Panel del Owner",
        is_system=False, position=0, created_by=owner_user.id,
    )
    db.add(panel)
    await db.flush()

    r = await client.delete(f"/api/dashboard/panels/{panel.id}", headers=auth(manager_token))
    assert r.status_code == 403, r.text


async def test_delete_custom_panel_forbidden_even_for_owner_role(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch, owner_token: str,
) -> None:
    """403 aplica incluso si quien intenta borrar tiene rol owner — solo el creador puede."""
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    other_owner = User(
        tenant_id=tenant.id, branch_id=branch.id,
        email=f"otro-owner-{uuid.uuid4().hex[:6]}@walix.test", name="Otro Owner",
        hashed_password=hash_password("test1234"), role=UserRole.OWNER, is_active=True,
    )
    db.add(other_owner)
    await db.flush()

    panel = DashboardPanel(
        tenant_id=tenant.id, key="panel-otro-owner", name="Panel de Otro Owner",
        is_system=False, position=0, created_by=other_owner.id,
    )
    db.add(panel)
    await db.flush()

    r = await client.delete(f"/api/dashboard/panels/{panel.id}", headers=auth(owner_token))
    assert r.status_code == 403, r.text


async def test_delete_system_panel_is_protected(
    client: AsyncClient, system_panels: dict, owner_token: str,
) -> None:
    r = await client.delete(
        f"/api/dashboard/panels/{system_panels['principal'].id}", headers=auth(owner_token)
    )
    assert r.status_code == 403, r.text


async def test_delete_own_custom_panel_succeeds(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, owner_user: User, owner_token: str,
) -> None:
    panel = DashboardPanel(
        tenant_id=tenant.id, key="panel-a-borrar", name="Panel a Borrar",
        is_system=False, position=0, created_by=owner_user.id,
    )
    db.add(panel)
    await db.flush()

    r = await client.delete(f"/api/dashboard/panels/{panel.id}", headers=auth(owner_token))
    assert r.status_code == 204, r.text


# ── Catálogo de widgets por panel ─────────────────────────────────────────────

async def test_system_panel_catalog_filters_by_exact_surface(
    client: AsyncClient, system_panels: dict, widgets_multi_surface: dict, owner_token: str,
) -> None:
    """El panel 'principal' (is_system) solo devuelve widgets con surface=='principal'."""
    r = await client.get(
        "/api/dashboard/widgets-catalog", params={"panel": "principal"}, headers=auth(owner_token)
    )
    assert r.status_code == 200, r.text
    keys = {w["key"] for w in r.json()}
    assert widgets_multi_surface["principal"].key in keys
    assert widgets_multi_surface["desempeno"].key not in keys
    assert widgets_multi_surface["other"].key not in keys


async def test_custom_panel_catalog_not_filtered_by_exact_surface(
    client: AsyncClient, widgets_multi_surface: dict, owner_token: str,
) -> None:
    """Regresión (bug corregido en Prompt 5): un panel custom debe devolver TODOS
    los widgets activos, sin filtrar por surface — antes solo devolvía los que
    coincidían exactamente con `surface == panel.key`, dejando paneles custom
    prácticamente vacíos."""
    create_r = await client.post(
        "/api/dashboard/panels", json={"name": "Panel Custom Sin Filtro"}, headers=auth(owner_token)
    )
    assert create_r.status_code == 201, create_r.text
    custom_key = create_r.json()["key"]

    r = await client.get(
        "/api/dashboard/widgets-catalog", params={"panel": custom_key}, headers=auth(owner_token)
    )
    assert r.status_code == 200, r.text
    keys = {w["key"] for w in r.json()}
    # Los 3 widgets (de superficies distintas) deben aparecer todos en un panel custom.
    assert widgets_multi_surface["principal"].key in keys
    assert widgets_multi_surface["desempeno"].key in keys
    assert widgets_multi_surface["other"].key in keys


async def test_desempeno_panel_gate_is_enforced_server_side(
    client: AsyncClient, system_panels: dict, widgets_multi_surface: dict,
    owner_token: str, asesor_token: str,
) -> None:
    """El gate del panel 'Desempeño' (min_role=owner) es del backend, no solo del cliente."""
    forbidden = await client.get(
        "/api/dashboard/widgets-catalog", params={"panel": "desempeno"}, headers=auth(asesor_token)
    )
    assert forbidden.status_code == 403, forbidden.text

    allowed = await client.get(
        "/api/dashboard/widgets-catalog", params={"panel": "desempeno"}, headers=auth(owner_token)
    )
    assert allowed.status_code == 200, allowed.text
    keys = {w["key"] for w in allowed.json()}
    assert widgets_multi_surface["desempeno"].key in keys
    assert widgets_multi_surface["principal"].key not in keys
