"""Dashboard configurable — widget catalog + layout endpoints.

Routes:
  GET  /api/dashboard/widgets-catalog          — catálogo activo filtrado por rol
  GET  /api/dashboard/layout                   — layout efectivo resuelto (cascada)
  PUT  /api/dashboard/layout?scope=user        — guarda layout personal
  PUT  /api/dashboard/layout?scope=role&role=X — guarda layout por rol (admin only)
  PUT  /api/dashboard/layout?scope=tenant_default — guarda default tenant (admin only)
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.dashboard_layout import DashboardLayout, DashboardWidget
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


async def _get_active_visible_widgets(
    user: User, db: AsyncSession
) -> list[DashboardWidget]:
    rows = (
        await db.execute(
            select(DashboardWidget)
            .where(
                DashboardWidget.is_active.is_(True),
                DashboardWidget.surface == "dashboard",
            )
            .order_by(DashboardWidget.default_position)
        )
    ).scalars().all()
    return [w for w in rows if _user_can_see_widget(user, w)]


async def _resolve_layout(
    user: User, db: AsyncSession
) -> list[ResolvedLayoutItem]:
    """Cascades user → role → tenant_default → catalog default."""
    widgets = await _get_active_visible_widgets(user, db)
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
    items: list[LayoutItem],
    db: AsyncSession,
) -> None:
    """Validates all keys exist in catalog, then upserts the layout."""
    # Validate every key
    all_keys_result = await db.execute(
        select(DashboardWidget.key).where(
            DashboardWidget.is_active.is_(True),
            DashboardWidget.surface == "dashboard",
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
            scope=scope,
            items=items_data,
        ))

    await db.commit()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@widgets_router.get("/widgets-catalog", response_model=list[WidgetOut])
async def list_widgets_catalog(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WidgetOut]:
    """Returns all active widgets visible to the current user's role."""
    widgets = await _get_active_visible_widgets(current_user, db)
    return [WidgetOut.model_validate(w) for w in widgets]


@widgets_router.get("/layout", response_model=list[ResolvedLayoutItem])
async def get_resolved_layout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ResolvedLayoutItem]:
    """Returns the effective layout for the current user after cascading scopes."""
    return await _resolve_layout(current_user, db)


@widgets_router.put("/layout", status_code=204)
async def save_layout(
    body: LayoutSaveRequest,
    scope: str = Query(
        ...,
        description="'user', 'role', or 'tenant_default'",
        pattern="^(user|role|tenant_default)$",
    ),
    role: str | None = Query(default=None, description="Required when scope=role"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
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
        items=body.items,
        db=db,
    )
