"""
Sprint 8A · P-02 — SavedViews CRUD endpoints
Prueba los 5 endpoints de /api/v1/contacts/views.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.saved_view import SavedView
from app.models.user import User

# ── helpers ───────────────────────────────────────────────────────────────────

_BASE = "/api/v1/contacts/views"


def _h(token_header: dict[str, str]) -> dict[str, str]:
    """Pass-through — fixtures already yield the full header dict."""
    return token_header


# ── P-02-01 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_views_empty(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """GET /contacts/views retorna lista vacía si el usuario no tiene vistas."""
    resp = await client.get(_BASE, headers=auth_asesor)
    assert resp.status_code == 200
    assert resp.json() == []


# ── P-02-02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_view_basic(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """POST /contacts/views crea una vista correctamente (201)."""
    payload = {
        "name": "Mis calificados",
        "filters": {"status": ["calificado"]},
        "view_mode": "list",
        "is_default": False,
    }
    resp = await client.post(_BASE, json=payload, headers=auth_asesor)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Mis calificados"
    assert data["filters"] == {"status": ["calificado"]}
    assert data["view_mode"] == "list"
    assert data["is_default"] is False
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


# ── P-02-03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_view_default_resets_others(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """Crear una vista como default pone las demás en is_default=False."""
    # Primera vista — default
    r1 = await client.post(
        _BASE,
        json={"name": "Vista A", "filters": {}, "view_mode": "list", "is_default": True},
        headers=auth_asesor,
    )
    assert r1.status_code == 201
    assert r1.json()["is_default"] is True

    # Segunda vista — también default
    r2 = await client.post(
        _BASE,
        json={"name": "Vista B", "filters": {}, "view_mode": "kanban", "is_default": True},
        headers=auth_asesor,
    )
    assert r2.status_code == 201
    assert r2.json()["is_default"] is True

    # Vista A ya no debe ser default
    views = (await client.get(_BASE, headers=auth_asesor)).json()
    vista_a = next(v for v in views if v["name"] == "Vista A")
    assert vista_a["is_default"] is False, "La vista anterior debería haber perdido el default"


# ── P-02-04 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_view_duplicate_name_fails(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """POST /contacts/views con nombre duplicado retorna 409."""
    payload = {"name": "Duplicada", "filters": {}, "view_mode": "list", "is_default": False}
    r1 = await client.post(_BASE, json=payload, headers=auth_asesor)
    assert r1.status_code == 201

    r2 = await client.post(_BASE, json=payload, headers=auth_asesor)
    assert r2.status_code == 409
    assert "nombre" in r2.json()["detail"].lower()


# ── P-02-05 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_views_ordered_default_first(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """GET /contacts/views retorna la vista default en primer lugar."""
    await client.post(
        _BASE,
        json={"name": "Normal", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_asesor,
    )
    await client.post(
        _BASE,
        json={"name": "Principal", "filters": {}, "view_mode": "kanban", "is_default": True},
        headers=auth_asesor,
    )

    views = (await client.get(_BASE, headers=auth_asesor)).json()
    assert len(views) >= 2
    assert views[0]["is_default"] is True
    assert views[0]["name"] == "Principal"


# ── P-02-06 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_view_rename(
    client: AsyncClient,
    auth_asesor: dict,
    saved_view_basic: SavedView,
) -> None:
    """PATCH /contacts/views/{id} renombra la vista correctamente."""
    resp = await client.patch(
        f"{_BASE}/{saved_view_basic.id}",
        json={"name": "Nombre actualizado"},
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Nombre actualizado"
    # Otros campos no deben cambiar
    assert resp.json()["view_mode"] == saved_view_basic.view_mode
    assert resp.json()["is_default"] == saved_view_basic.is_default


# ── P-02-07 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_view_of_other_user_fails(
    client: AsyncClient,
    auth_asesor: dict,
    auth_gerente: dict,
) -> None:
    """PATCH de una vista de otro usuario retorna 404 (aislamiento por user_id)."""
    # Gerente crea una vista
    r = await client.post(
        _BASE,
        json={"name": "Vista Gerente", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_gerente,
    )
    assert r.status_code == 201
    view_id = r.json()["id"]

    # Asesor intenta editar la vista del gerente → 404
    resp = await client.patch(
        f"{_BASE}/{view_id}",
        json={"name": "Hackeada"},
        headers=auth_asesor,
    )
    assert resp.status_code == 404


# ── P-02-08 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_view(
    client: AsyncClient,
    auth_asesor: dict,
    saved_view_basic: SavedView,
) -> None:
    """DELETE /contacts/views/{id} elimina la vista y retorna 204."""
    view_id = str(saved_view_basic.id)

    resp = await client.delete(f"{_BASE}/{view_id}", headers=auth_asesor)
    assert resp.status_code == 204

    # Verificar que ya no aparece en el listado
    views = (await client.get(_BASE, headers=auth_asesor)).json()
    assert not any(v["id"] == view_id for v in views)


# ── P-02-09 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_default_view_promotes_next(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """Al eliminar la vista default, la más reciente queda como nueva default."""
    # Crear dos vistas; la segunda es default
    r1 = await client.post(
        _BASE,
        json={"name": "Primera", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_asesor,
    )
    r2 = await client.post(
        _BASE,
        json={"name": "Default", "filters": {}, "view_mode": "list", "is_default": True},
        headers=auth_asesor,
    )
    assert r2.json()["is_default"] is True
    default_id = r2.json()["id"]

    # Eliminar la default
    await client.delete(f"{_BASE}/{default_id}", headers=auth_asesor)

    # La vista restante debe haberse promovido a default
    views = (await client.get(_BASE, headers=auth_asesor)).json()
    assert len(views) == 1
    assert views[0]["is_default"] is True
    assert views[0]["name"] == "Primera"


# ── P-02-10 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_default_view(
    client: AsyncClient,
    auth_asesor: dict,
    saved_view_basic: SavedView,
) -> None:
    """POST /contacts/views/{id}/set-default marca la vista como default."""
    resp = await client.post(
        f"{_BASE}/{saved_view_basic.id}/set-default",
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["is_default"] is True
    assert data["id"] == str(saved_view_basic.id)


# ── P-02-11 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_default_clears_previous(
    client: AsyncClient,
    auth_asesor: dict,
    saved_view_basic: SavedView,
    saved_view_default: SavedView,
) -> None:
    """set-default limpia el default anterior antes de asignar el nuevo."""
    assert saved_view_default.is_default is True

    # Marcar saved_view_basic como default
    resp = await client.post(
        f"{_BASE}/{saved_view_basic.id}/set-default",
        headers=auth_asesor,
    )
    assert resp.status_code == 200

    # Verificar que saved_view_default ya no es default
    views = (await client.get(_BASE, headers=auth_asesor)).json()
    prev_default = next(v for v in views if v["id"] == str(saved_view_default.id))
    assert prev_default["is_default"] is False


# ── P-02-12 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_view_limit_enforced(
    client: AsyncClient,
    auth_asesor: dict,
    multiple_views: list[SavedView],  # pre-crea 10 vistas
) -> None:
    """No se pueden crear más de 10 vistas (límite plan Starter/Growth)."""
    assert len(multiple_views) == 10  # fixture garantiza exactamente 10

    resp = await client.post(
        _BASE,
        json={"name": "Vista 11", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_asesor,
    )
    assert resp.status_code == 422
    assert "Límite" in resp.json()["detail"]


# ── P-02-13 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_views_isolated_by_user(
    client: AsyncClient,
    auth_asesor: dict,
    auth_gerente: dict,
    saved_view_basic: SavedView,
) -> None:
    """Cada usuario solo ve sus propias vistas — aislamiento por user_id."""
    # Gerente no ve las vistas del asesor
    views_gerente = (await client.get(_BASE, headers=auth_gerente)).json()
    asesor_view_ids = {str(saved_view_basic.id)}
    assert not any(v["id"] in asesor_view_ids for v in views_gerente)

    # Asesor sí ve su propia vista
    views_asesor = (await client.get(_BASE, headers=auth_asesor)).json()
    assert any(v["id"] == str(saved_view_basic.id) for v in views_asesor)


# ── P-02-14 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_view_invalid_mode_fails(
    client: AsyncClient,
    auth_asesor: dict,
    saved_view_basic: SavedView,
) -> None:
    """PATCH con view_mode inválido retorna 422."""
    resp = await client.patch(
        f"{_BASE}/{saved_view_basic.id}",
        json={"view_mode": "table"},
        headers=auth_asesor,
    )
    assert resp.status_code == 422


# ── P-02-15 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_view_name_strip_whitespace(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """El nombre se recorta de espacios antes de guardar."""
    resp = await client.post(
        _BASE,
        json={"name": "  Espacios  ", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_asesor,
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Espacios"


# ── P-02-16 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_view_empty_name_fails(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """POST con nombre vacío o solo espacios retorna 422."""
    resp = await client.post(
        _BASE,
        json={"name": "   ", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_asesor,
    )
    assert resp.status_code == 422
