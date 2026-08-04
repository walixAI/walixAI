"""Message templates — branch-scoped and tenant-wide WhatsApp template catalog.

Routes (branch-scoped):
  GET    /api/branches/{branch_id}/message-templates
  POST   /api/branches/{branch_id}/message-templates

Routes (tenant-level):
  POST   /api/message-templates               (tenant-wide, owner/IT only)
  PATCH  /api/message-templates/{id}
  DELETE /api/message-templates/{id}          (soft-delete: is_active=False)
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.message_template import MessageTemplate
from app.models.tenant import Branch
from app.models.user import User, UserRole

branch_templates_router = APIRouter(prefix="/branches", tags=["message-templates"])
templates_router = APIRouter(prefix="/message-templates", tags=["message-templates"])

_ADMIN_ROLES = (UserRole.OWNER, UserRole.IT)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TemplateOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID | None
    name: str
    language: str
    category: str
    body_preview: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TemplateCreateRequest(BaseModel):
    name: str
    language: str = "es_MX"
    category: str = "General"
    body_preview: str | None = None


class TemplatePatchRequest(BaseModel):
    name: str | None = None
    language: str | None = None
    category: str | None = None
    body_preview: str | None = None
    is_active: bool | None = None


# ── Access helpers ────────────────────────────────────────────────────────────

async def _get_branch(branch_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> Branch:
    branch = await db.get(Branch, branch_id)
    if not branch or branch.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    return branch


def _require_branch_write(user: User, branch: Branch) -> None:
    """OWNER/IT can write to any branch; GERENTE only their own."""
    if user.role in _ADMIN_ROLES:
        return
    if user.role == UserRole.GERENTE and user.branch_id == branch.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Solo owner, IT, o el gerente de esta sucursal pueden gestionar sus plantillas",
    )


async def _get_template(
    template_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> MessageTemplate:
    tmpl = await db.get(MessageTemplate, template_id)
    if not tmpl or tmpl.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return tmpl


def _require_template_write(user: User, tmpl: MessageTemplate) -> None:
    """Tenant-wide templates: owner/IT only. Branch templates: owner/IT/branch-gerente."""
    if user.role in _ADMIN_ROLES:
        return
    if tmpl.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo owner o IT pueden modificar plantillas tenant-wide",
        )
    if user.role == UserRole.GERENTE and user.branch_id == tmpl.branch_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes permiso para modificar esta plantilla",
    )


# ── Branch-scoped routes ──────────────────────────────────────────────────────

@branch_templates_router.get("/{branch_id}/message-templates", response_model=list[TemplateOut])
async def list_branch_templates(
    branch_id: uuid.UUID,
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TemplateOut]:
    """Returns branch-specific templates PLUS tenant-wide templates (branch_id IS NULL).
    Only active by default; pass include_inactive=true for the admin view.
    """
    await _get_branch(branch_id, current_user.tenant_id, db)

    q = select(MessageTemplate).where(
        MessageTemplate.tenant_id == current_user.tenant_id,
        or_(
            MessageTemplate.branch_id == branch_id,
            MessageTemplate.branch_id.is_(None),
        ),
    )
    if not include_inactive:
        q = q.where(MessageTemplate.is_active.is_(True))
    q = q.order_by(MessageTemplate.category, MessageTemplate.name)

    rows = (await db.execute(q)).scalars().all()
    return [TemplateOut.model_validate(r) for r in rows]


@branch_templates_router.post(
    "/{branch_id}/message-templates",
    response_model=TemplateOut,
    status_code=201,
)
async def create_branch_template(
    branch_id: uuid.UUID,
    body: TemplateCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    """Creates a template scoped to this branch."""
    branch = await _get_branch(branch_id, current_user.tenant_id, db)
    _require_branch_write(current_user, branch)

    tmpl = MessageTemplate(
        tenant_id=current_user.tenant_id,
        branch_id=branch_id,
        name=body.name,
        language=body.language,
        category=body.category,
        body_preview=body.body_preview,
        is_active=True,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return TemplateOut.model_validate(tmpl)


# ── Tenant-wide routes ────────────────────────────────────────────────────────

@templates_router.post("", response_model=TemplateOut, status_code=201)
async def create_tenant_template(
    body: TemplateCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    """Creates a tenant-wide template (branch_id=NULL). Owner/IT only."""
    if current_user.role not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo owner o IT pueden crear plantillas tenant-wide",
        )
    tmpl = MessageTemplate(
        tenant_id=current_user.tenant_id,
        branch_id=None,
        name=body.name,
        language=body.language,
        category=body.category,
        body_preview=body.body_preview,
        is_active=True,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return TemplateOut.model_validate(tmpl)


@templates_router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: uuid.UUID,
    body: TemplatePatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    tmpl = await _get_template(template_id, current_user.tenant_id, db)
    _require_template_write(current_user, tmpl)

    if body.name is not None:
        tmpl.name = body.name
    if body.language is not None:
        tmpl.language = body.language
    if body.category is not None:
        tmpl.category = body.category
    if body.body_preview is not None:
        tmpl.body_preview = body.body_preview
    if body.is_active is not None:
        tmpl.is_active = body.is_active
    tmpl.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(tmpl)
    return TemplateOut.model_validate(tmpl)


@templates_router.delete("/{template_id}", status_code=204)
async def deactivate_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete (is_active=False) to preserve references in sent messages."""
    tmpl = await _get_template(template_id, current_user.tenant_id, db)
    _require_template_write(current_user, tmpl)

    tmpl.is_active = False
    tmpl.updated_at = datetime.now(timezone.utc)
    await db.commit()
