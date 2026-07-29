import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.lead import Lead, LeadStatus
from app.models.meta_ads import MetaLeadConfig
from app.models.pipeline import PipelineStage
from app.models.pipeline_group import Pipeline
from app.models.tenant import Branch
from app.models.user import User, UserRole

router = APIRouter(prefix="/branches", tags=["branches"])

_ACTIVE_STATUSES = (LeadStatus.CALIFICADO, LeadStatus.EN_CALIFICACION)


class BranchOut(BaseModel):
    id: uuid.UUID
    name: str


@router.get("", response_model=list[BranchOut])
async def list_branches(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BranchOut]:
    """Returns all branches the user can access (their own branch, or all in the tenant for owner/IT)."""
    if current_user.role in (UserRole.OWNER, UserRole.IT):
        rows = await db.execute(
            select(Branch).where(Branch.tenant_id == current_user.tenant_id).order_by(Branch.name)
        )
    elif current_user.branch_id:
        rows = await db.execute(select(Branch).where(Branch.id == current_user.branch_id))
    else:
        return []
    return [BranchOut(id=b.id, name=b.name) for b in rows.scalars().all()]
_AGENT_ROLES = (UserRole.DOCTOR, UserRole.ASESOR, UserRole.GERENTE)


class AgentOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    active_leads: int
    wa_phone: str | None


async def _require_branch_access(
    user: User, branch_id: uuid.UUID, db: AsyncSession
) -> None:
    """Raises 403 if the user has no access to the given branch."""
    if user.branch_id == branch_id:
        return
    if user.role in (UserRole.OWNER, UserRole.IT, UserRole.GERENTE):
        branch = await db.get(Branch, branch_id)
        if branch and branch.tenant_id == user.tenant_id:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes acceso a esta sucursal",
    )


@router.get("/{branch_id}/agents", response_model=list[AgentOut])
async def list_branch_agents(
    branch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentOut]:
    """Returns active agents in the branch ordered by workload (fewest active leads first).

    Active leads = leads with status calificado or en_calificacion assigned to the user.
    Doctors appear before asesores, who appear before gerentes.
    """
    await _require_branch_access(current_user, branch_id, db)

    # Correlated subquery: count active leads assigned to each user
    active_leads_sq = (
        select(func.count(Lead.id))
        .where(
            Lead.assigned_to == User.id,
            Lead.status.in_(_ACTIVE_STATUSES),
        )
        .correlate(User)
        .scalar_subquery()
    )

    rows = await db.execute(
        select(User, active_leads_sq.label("active_leads"))
        .where(
            User.branch_id == branch_id,
            User.is_active.is_(True),
            User.role.in_(_AGENT_ROLES),
        )
    )

    role_order = {UserRole.DOCTOR: 0, UserRole.ASESOR: 1, UserRole.GERENTE: 2}
    agents: list[AgentOut] = []
    for user, active_leads in rows.all():
        agents.append(
            AgentOut(
                id=user.id,
                name=user.name,
                role=user.role,
                active_leads=active_leads,
                wa_phone=user.wa_phone,
            )
        )

    agents.sort(key=lambda a: (role_order.get(UserRole(a.role), 9), a.active_leads))
    return agents


# ── Bot / onboarding config ───────────────────────────────────────────────────

_BOT_CONFIG_ROLES = (UserRole.OWNER, UserRole.GERENTE, UserRole.IT)
_BOT_REGEN_ROLES = (UserRole.OWNER, UserRole.IT)


class BotConfigOut(BaseModel):
    """Spec-compliant bot config response (Sprint 12 §5)."""
    # Meta
    branch_name: str
    onboarding_status: str
    bot_name: str | None
    industry: str | None
    business_description: str | None
    latest_draft_id: uuid.UUID | None
    onboarding_description: str | None = None
    # Config (spec-compliant names)
    system_prompt: str | None = None
    tone: str | None = None
    qualification_questions: list | None = None
    bot_config_generated_at: str | None = None
    bot_config_updated_at: str | None = None
    is_auto_generated: bool = False  # True cuando no ha sido editado manualmente


class BotConfigUpdateIn(BaseModel):
    system_prompt: str | None = None
    tone: str | None = None
    qualification_questions: list | None = None


def _build_bot_config_out(branch: Branch, tenant: Any | None, latest_draft_id: uuid.UUID | None) -> BotConfigOut:
    return BotConfigOut(
        branch_name=branch.name,
        onboarding_status=branch.onboarding_status,
        bot_name=branch.bot_name,
        industry=branch.industry,
        business_description=branch.business_description,
        latest_draft_id=latest_draft_id,
        onboarding_description=tenant.onboarding_description if tenant else None,
        system_prompt=branch.bot_system_prompt,
        tone=branch.bot_tone,
        qualification_questions=branch.bot_qualification_questions,
        bot_config_generated_at=branch.bot_config_generated_at.isoformat() if branch.bot_config_generated_at else None,
        bot_config_updated_at=branch.bot_config_updated_at.isoformat() if branch.bot_config_updated_at else None,
        is_auto_generated=branch.bot_system_prompt is not None and branch.bot_config_updated_at is None,
    )


async def _latest_draft_id(branch_id: uuid.UUID, db: AsyncSession) -> uuid.UUID | None:
    from app.models.onboarding import OnboardingDraft
    from sqlalchemy import desc
    row = (await db.execute(
        select(OnboardingDraft).where(OnboardingDraft.branch_id == branch_id)
        .order_by(desc(OnboardingDraft.created_at)).limit(1)
    )).scalar_one_or_none()
    return row.id if row else None


@router.get("/{branch_id}/bot-config", response_model=BotConfigOut)
async def get_bot_config(
    branch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotConfigOut:
    """Retorna la config actual del bot (roles: owner, gerente, it)."""
    from app.models.tenant import Tenant

    if current_user.role not in _BOT_CONFIG_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
    await _require_branch_access(current_user, branch_id, db)
    branch = await db.get(Branch, branch_id)
    if not branch or branch.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada")

    tenant = await db.get(Tenant, branch.tenant_id)
    return _build_bot_config_out(branch, tenant, await _latest_draft_id(branch_id, db))


@router.patch("/{branch_id}/bot-config", response_model=BotConfigOut)
async def update_bot_config(
    branch_id: uuid.UUID,
    body: BotConfigUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotConfigOut:
    """Actualiza parcialmente la config del bot (roles: owner, gerente, it)."""
    from datetime import datetime, timezone
    from app.models.tenant import Tenant

    if current_user.role not in _BOT_CONFIG_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
    await _require_branch_access(current_user, branch_id, db)
    branch = await db.get(Branch, branch_id)
    if not branch or branch.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada")

    if body.system_prompt is not None:
        branch.bot_system_prompt = body.system_prompt
    if body.tone is not None:
        branch.bot_tone = body.tone
    if body.qualification_questions is not None:
        branch.bot_qualification_questions = body.qualification_questions
    branch.bot_config_updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(branch)

    tenant = await db.get(Tenant, branch.tenant_id)
    return _build_bot_config_out(branch, tenant, await _latest_draft_id(branch_id, db))


@router.post("/{branch_id}/bot-config/regenerate")
async def regenerate_bot_config(
    branch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-genera la config del bot desde la descripción original del onboarding (roles: owner, it)."""
    from app.models.tenant import Tenant
    from app.services.bot_config_generator import bot_config_generator

    if current_user.role not in _BOT_REGEN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o IT pueden regenerar la config")
    await _require_branch_access(current_user, branch_id, db)
    branch = await db.get(Branch, branch_id)
    if not branch or branch.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada")

    tenant = await db.get(Tenant, branch.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")

    config = await bot_config_generator.regenerate_for_branch(branch=branch, tenant=tenant, db=db)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No hay descripción del negocio disponible para generar la configuración",
        )

    await db.commit()
    return {
        "message": "Configuración regenerada.",
        "bot_config": {
            "system_prompt": config["system_prompt"],
            "tone": config["tone"],
            "qualification_questions": config["qualification_questions"],
        },
    }


# ── Meta Lead Ads config ───────────────────────────────────────────────────────

_META_ROLES = (UserRole.OWNER, UserRole.IT)

_DEFAULT_FIELD_MAPPING: dict[str, str] = {
    "full_name": "name",
    "phone_number": "wa_phone",
    "city": "parent_city",
}


class MetaConfigIn(BaseModel):
    page_id: str
    page_access_token: str
    form_ids: list[str] = []
    field_mapping: dict[str, Any] = _DEFAULT_FIELD_MAPPING


class MetaConfigOut(BaseModel):
    page_id: str
    form_ids: list[str]
    field_mapping: dict[str, Any]
    is_active: bool
    verify_token: str


async def _require_meta_access(user: User, branch_id: uuid.UUID, db: AsyncSession) -> Branch:
    branch = await db.get(Branch, branch_id)
    if not branch or branch.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada")
    if user.role not in _META_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o IT pueden gestionar esta configuracion")
    return branch


@router.get("/{branch_id}/meta-config", response_model=MetaConfigOut | None)
async def get_meta_config(
    branch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MetaConfigOut | None:
    await _require_meta_access(current_user, branch_id, db)
    result = await db.execute(
        select(MetaLeadConfig).where(
            MetaLeadConfig.branch_id == branch_id,
            MetaLeadConfig.is_active.is_(True),
        )
    )
    cfg = result.scalars().first()
    if not cfg:
        return None
    return MetaConfigOut(
        page_id=cfg.page_id,
        form_ids=cfg.form_ids or [],
        field_mapping=cfg.field_mapping or _DEFAULT_FIELD_MAPPING,
        is_active=cfg.is_active,
        verify_token=settings.META_VERIFY_TOKEN,
    )


@router.post("/{branch_id}/meta-config", response_model=MetaConfigOut)
async def save_meta_config(
    branch_id: uuid.UUID,
    body: MetaConfigIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MetaConfigOut:
    branch = await _require_meta_access(current_user, branch_id, db)

    result = await db.execute(
        select(MetaLeadConfig).where(MetaLeadConfig.branch_id == branch_id)
    )
    cfg = result.scalars().first()

    if cfg:
        cfg.page_id = body.page_id
        cfg.page_access_token = body.page_access_token  # stored as-is (same as wa_token)
        cfg.form_ids = body.form_ids
        cfg.field_mapping = body.field_mapping
        cfg.is_active = True
    else:
        cfg = MetaLeadConfig(
            id=uuid.uuid4(),
            branch_id=branch_id,
            tenant_id=branch.tenant_id,
            page_id=body.page_id,
            page_access_token=body.page_access_token,
            form_ids=body.form_ids,
            field_mapping=body.field_mapping,
            is_active=True,
        )
        db.add(cfg)

    await db.commit()

    return MetaConfigOut(
        page_id=cfg.page_id,
        form_ids=cfg.form_ids or [],
        field_mapping=cfg.field_mapping or _DEFAULT_FIELD_MAPPING,
        is_active=cfg.is_active,
        verify_token=settings.META_VERIFY_TOKEN,
    )


@router.delete("/{branch_id}/meta-config", status_code=204)
async def delete_meta_config(
    branch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _require_meta_access(current_user, branch_id, db)
    result = await db.execute(
        select(MetaLeadConfig).where(MetaLeadConfig.branch_id == branch_id)
    )
    cfg = result.scalars().first()
    if cfg:
        cfg.is_active = False
        await db.commit()


# ── Pipeline stages ────────────────────────────────────────────────────────────


class PipelineStageOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    order_index: int
    color: str | None
    is_won: bool
    is_lost: bool
    pipeline_id: uuid.UUID


@router.get("/{branch_id}/pipeline", response_model=list[PipelineStageOut])
async def get_branch_pipeline(
    branch_id: uuid.UUID,
    pipeline_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PipelineStageOut]:
    """Returns active pipeline stages for a branch ordered by order_index.

    If pipeline_id is provided, returns stages for that specific pipeline
    (must belong to the branch). If omitted, uses the branch's default pipeline.
    Returns empty list if no default pipeline exists.
    """
    await _require_branch_access(current_user, branch_id, db)

    if pipeline_id is not None:
        # Validate the requested pipeline belongs to this branch
        pipeline = await db.get(Pipeline, pipeline_id)
        if pipeline is None or pipeline.branch_id != branch_id:
            raise HTTPException(status_code=404, detail="Pipeline no encontrado en esta branch")
        resolved_pipeline_id = pipeline_id
    else:
        # Fall back to the branch's default pipeline
        default_result = await db.execute(
            select(Pipeline.id).where(
                Pipeline.branch_id == branch_id,
                Pipeline.is_default.is_(True),
            ).limit(1)
        )
        resolved_pipeline_id = default_result.scalar_one_or_none()
        if resolved_pipeline_id is None:
            return []

    rows = await db.execute(
        select(PipelineStage)
        .where(
            PipelineStage.branch_id == branch_id,
            PipelineStage.pipeline_id == resolved_pipeline_id,
            PipelineStage.is_active.is_(True),
        )
        .order_by(PipelineStage.order_index)
    )
    return [
        PipelineStageOut(
            id=s.id,
            name=s.name,
            slug=s.slug,
            order_index=s.order_index,
            color=s.color,
            is_won=s.is_won,
            is_lost=s.is_lost,
            pipeline_id=s.pipeline_id,
        )
        for s in rows.scalars().all()
    ]
