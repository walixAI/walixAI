"""Dashboard configurable — widget catalog + layout endpoints + panel management.

Routes:
  GET  /api/dashboard/panels                     — lista paneles visibles al usuario
  POST /api/dashboard/panels                     — crea panel personalizado
  DELETE /api/dashboard/panels/{id}              — elimina panel personalizado (solo dueño)

  GET  /api/dashboard/widgets-catalog            — catálogo activo filtrado por rol
  GET  /api/dashboard/layout?panel=principal     — layout efectivo resuelto (cascada)
  PUT  /api/dashboard/layout?scope=user&panel=X  — guarda layout personal en el panel
  PUT  /api/dashboard/layout?scope=role&role=X&panel=X — guarda layout por rol (admin only)
  PUT  /api/dashboard/layout?scope=tenant_default&panel=X — guarda default tenant (admin only)
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.dashboard_layout import DashboardLayout, DashboardPanel, DashboardWidget
from app.models.user import User, UserRole

widgets_router = APIRouter(prefix="/dashboard", tags=["dashboard-config"])

_ADMIN_ROLES = (UserRole.OWNER, UserRole.IT)

# Role rank for min_role filtering (higher = more privileged)
_ROLE_RANK: dict[UserRole, int] = {
    UserRole.PLATFORM_OWNER: 100,
    UserRole.OWNER: 90,
    UserRole.IT: 80,
    UserRole.GERENTE: 70,
    UserRole.DOCTOR: 50,
    UserRole.ASESOR: 40,
    UserRole.SOPORTE: 30,
}


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class WidgetOut(BaseModel):
    key: str
    name: str
    description: str | None
    native_key: str
    min_role: str | None
    is_active: bool
    is_mandatory: bool
    default_position: int
    surface: str

    model_config = {"from_attributes": True}


class LayoutItem(BaseModel):
    key: str
    position: int
    hidden: bool = False


class LayoutSaveRequest(BaseModel):
    items: list[LayoutItem]


class ResolvedLayoutItem(BaseModel):
    key: str
    position: int
    hidden: bool
    is_mandatory: bool


class PanelOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    icon: str | None
    min_role: str | None
    is_system: bool
    position: int
    created_by: uuid.UUID | None

    model_config = {"from_attributes": True}


class PanelCreateRequest(BaseModel):
    name: str
    icon: str | None = None
    min_role: str | None = None
    position: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _user_can_see_widget(user: User, widget: DashboardWidget) -> bool:
    """Returns True if the user's role meets the widget's min_role requirement."""
    if widget.min_role is None:
        return True
    try:
        required = UserRole(widget.min_role)
    except ValueError:
        return True
    return _ROLE_RANK.get(user.role, 0) >= _ROLE_RANK.get(required, 0)


def _user_can_see_panel(user: User, panel: DashboardPanel) -> bool:
    """Returns True if the user can access the given panel."""
    if panel.min_role is not None:
        try:
            required = UserRole(panel.min_role)
        except ValueError:
            pass
        else:
            if _ROLE_RANK.get(user.role, 0) < _ROLE_RANK.get(required, 0):
                return False
    if not panel.is_system and panel.created_by != user.id:
        return False
    return True


async def _get_panel_or_404(
    tenant_id: uuid.UUID,
    panel_key: str,
    user: User,
    db: AsyncSession,
) -> DashboardPanel:
    """Returns the panel or raises 404; also checks min_role and ownership."""
    row = (
        await db.execute(
            select(DashboardPanel).where(
                DashboardPanel.tenant_id == tenant_id,
                DashboardPanel.key == panel_key,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Panel '{panel_key}' no encontrado")

    if not _user_can_see_panel(user, row):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="No tienes acceso a este panel")
    return row


async def _get_active_visible_widgets(
    user: User, db: AsyncSession, panel_key: str = "principal"
) -> list[DashboardWidget]:
    rows = (
        await db.execute(
            select(DashboardWidget)
            .where(
                DashboardWidget.is_active.is_(True),
                DashboardWidget.surface == panel_key,
            )
            .order_by(DashboardWidget.default_position)
        )
    ).scalars().all()
    return [w for w in rows if _user_can_see_widget(user, w)]


async def _resolve_layout(
    user: User, db: AsyncSession, panel_key: str = "principal"
) -> list[ResolvedLayoutItem]:
    """Cascades user → role → tenant_default → catalog default for a given panel."""
    widgets = await _get_active_visible_widgets(user, db, panel_key=panel_key)
    widget_map = {w.key: w for w in widgets}

    scopes_to_try = [
        f"user:{user.id}",
        f"role:{user.role.value}",
        "tenant_default",
    ]

    saved_items: list[dict[str, Any]] | None = None
    for scope in scopes_to_try:
        row = (
            await db.execute(
                select(DashboardLayout).where(
                    DashboardLayout.tenant_id == user.tenant_id,
                    DashboardLayout.panel_key == panel_key,
                    DashboardLayout.scope == scope,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            saved_items = row.items  # type: ignore[assignment]
            break

    # Build final list by merging saved_items with catalog
    if saved_items:
        saved_map = {item["key"]: item for item in saved_items if item["key"] in widget_map}
    else:
        saved_map = {}

    result: list[ResolvedLayoutItem] = []
    for widget in widgets:
        saved = saved_map.get(widget.key)
        if saved:
            pos = saved.get("position", widget.default_position)
            hidden = bool(saved.get("hidden", False))
        else:
            pos = widget.default_position
            hidden = False

        # Mandatory widgets can never be hidden
        if widget.is_mandatory:
            hidden = False

        result.append(ResolvedLayoutItem(
            key=widget.key,
            position=pos,
            hidden=hidden,
            is_mandatory=widget.is_mandatory,
        ))

    result.sort(key=lambda x: x.position)
    return result


async def _validate_and_save_layout(
    tenant_id: uuid.UUID,
    scope: str,
    panel_key: str,
    items: list[LayoutItem],
    db: AsyncSession,
) -> None:
    """Validates all keys exist in catalog, then upserts the layout for panel_key."""
    # Validate every key
    all_keys_result = await db.execute(
        select(DashboardWidget.key).where(
            DashboardWidget.is_active.is_(True),
            DashboardWidget.surface == panel_key,
        )
    )
    valid_keys = {row[0] for row in all_keys_result.fetchall()}

    bad_keys = [item.key for item in items if item.key not in valid_keys]
    if bad_keys:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Widget keys no válidas o inactivas: {bad_keys}",
        )

    items_data = [{"key": i.key, "position": i.position, "hidden": i.hidden} for i in items]

    existing = (
        await db.execute(
            select(DashboardLayout).where(
                DashboardLayout.tenant_id == tenant_id,
                DashboardLayout.panel_key == panel_key,
                DashboardLayout.scope == scope,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.items = items_data  # type: ignore[assignment]
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(DashboardLayout(
            tenant_id=tenant_id,
            panel_key=panel_key,
            scope=scope,
            items=items_data,
        ))

    await db.commit()


# ── Panel endpoints ───────────────────────────────────────────────────────────

@widgets_router.get("/panels", response_model=list[PanelOut])
async def list_panels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PanelOut]:
    """Returns all panels the current user can access (system + own custom panels)."""
    rows = (
        await db.execute(
            select(DashboardPanel)
            .where(DashboardPanel.tenant_id == current_user.tenant_id)
            .order_by(DashboardPanel.position)
        )
    ).scalars().all()

    return [PanelOut.model_validate(p) for p in rows if _user_can_see_panel(current_user, p)]


@widgets_router.post("/panels", response_model=PanelOut, status_code=201)
async def create_panel(
    body: PanelCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PanelOut:
    """Creates a personal custom panel for the current user."""
    # Slug = lowercase alphanum + hyphens
    key = re.sub(r"[^a-z0-9]+", "-", body.name.lower().strip()).strip("-")
    if not key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="El nombre no produce una clave válida")

    # Check for duplicate within this user's custom panels
    conflict = (
        await db.execute(
            select(DashboardPanel).where(
                DashboardPanel.tenant_id == current_user.tenant_id,
                DashboardPanel.key == key,
                DashboardPanel.is_system.is_(False),
                DashboardPanel.created_by == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if conflict is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Ya tienes un panel con la clave '{key}'")

    panel = DashboardPanel(
        tenant_id=current_user.tenant_id,
        key=key,
        name=body.name,
        icon=body.icon,
        min_role=body.min_role,
        is_system=False,
        position=body.position,
        created_by=current_user.id,
    )
    db.add(panel)
    await db.commit()
    await db.refresh(panel)
    return PanelOut.model_validate(panel)


@widgets_router.delete("/panels/{panel_id}", status_code=204)
async def delete_panel(
    panel_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deletes a custom panel. Only the creator can delete it; system panels and panels owned by others are protected."""
    panel = await db.get(DashboardPanel, panel_id)
    if panel is None or panel.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panel no encontrado")

    if panel.is_system:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Los paneles del sistema no se pueden eliminar")

    if panel.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Solo el creador puede eliminar este panel")

    await db.delete(panel)
    await db.commit()


# ── Widget / layout endpoints ─────────────────────────────────────────────────

@widgets_router.get("/widgets-catalog", response_model=list[WidgetOut])
async def list_widgets_catalog(
    panel: str = Query(default="principal", description="Panel key (default: principal)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WidgetOut]:
    """Returns all active widgets visible to the current user's role."""
    await _get_panel_or_404(current_user.tenant_id, panel, current_user, db)
    widgets = await _get_active_visible_widgets(current_user, db, panel_key=panel)
    return [WidgetOut.model_validate(w) for w in widgets]


@widgets_router.get("/layout", response_model=list[ResolvedLayoutItem])
async def get_resolved_layout(
    panel: str = Query(default="principal", description="Panel key (default: principal)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ResolvedLayoutItem]:
    """Returns the effective layout for the current user after cascading scopes."""
    await _get_panel_or_404(current_user.tenant_id, panel, current_user, db)
    return await _resolve_layout(current_user, db, panel_key=panel)


@widgets_router.put("/layout", status_code=204)
async def save_layout(
    body: LayoutSaveRequest,
    panel: str = Query(default="principal", description="Panel key (default: principal)"),
    scope: str = Query(
        ...,
        description="'user', 'role', or 'tenant_default'",
        pattern="^(user|role|tenant_default)$",
    ),
    role: str | None = Query(default=None, description="Required when scope=role"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_panel_or_404(current_user.tenant_id, panel, current_user, db)

    if scope == "user":
        resolved_scope = f"user:{current_user.id}"

    elif scope == "role":
        if current_user.role not in _ADMIN_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Solo owner o IT pueden editar layouts por rol")
        if not role:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="El parámetro 'role' es requerido cuando scope=role")
        try:
            UserRole(role)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Rol inválido: {role}")
        resolved_scope = f"role:{role}"

    else:  # tenant_default
        if current_user.role not in _ADMIN_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Solo owner o IT pueden editar el layout por defecto del tenant")
        resolved_scope = "tenant_default"

    await _validate_and_save_layout(
        tenant_id=current_user.tenant_id,
        scope=resolved_scope,
        panel_key=panel,
        items=body.items,
        db=db,
    )
