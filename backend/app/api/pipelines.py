"""CRUD de Pipelines (multi-pipeline).

GET    /api/pipelines?branch_id={id}  — lista pipelines de la branch
POST   /api/pipelines                 — crea un nuevo pipeline
PATCH  /api/pipelines/{id}            — renombra o reordena
DELETE /api/pipelines/{id}            — borra (con guardas de seguridad)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.roles import MULTI_BRANCH_ROLES
from app.models.deal import Deal
from app.models.pipeline import PipelineStage
from app.models.pipeline_group import Pipeline, resolve_default_pipeline_id
from app.models.tenant import Branch
from app.models.user import User

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


# ── Schemas ────────────────────────────────────────────────────────────────────


class PipelineOut(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool
    position: int
    branch_id: uuid.UUID

    model_config = {"from_attributes": True}


class PipelineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    branch_id: uuid.UUID


class PipelineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    position: int | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _get_pipeline_or_404(
    pipeline_id: uuid.UUID, current_user: User, db: AsyncSession
) -> Pipeline:
    p = await db.get(Pipeline, pipeline_id)
    if p is None or p.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Pipeline no encontrado")
    return p


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("", response_model=list[PipelineOut])
async def list_pipelines(
    branch_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Pipeline]:
    if branch_id is not None:
        branch = await db.get(Branch, branch_id)
        if branch is None or branch.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=404, detail="Branch no encontrada")
        where = [Pipeline.branch_id == branch_id, Pipeline.tenant_id == current_user.tenant_id]
    elif current_user.role in MULTI_BRANCH_ROLES:
        # MULTI_BRANCH_ROLES: all pipelines across all branches of the tenant
        where = [Pipeline.tenant_id == current_user.tenant_id]
    elif current_user.branch_id is not None:
        where = [Pipeline.branch_id == current_user.branch_id, Pipeline.tenant_id == current_user.tenant_id]
    else:
        branch_result = await db.execute(
            select(Branch.id)
            .where(Branch.tenant_id == current_user.tenant_id, Branch.is_active.is_(True))
            .order_by(Branch.created_at.asc())
            .limit(1)
        )
        resolved_branch_id = branch_result.scalar_one_or_none()
        if resolved_branch_id is None:
            return []
        where = [Pipeline.branch_id == resolved_branch_id, Pipeline.tenant_id == current_user.tenant_id]

    result = await db.execute(
        select(Pipeline)
        .where(*where)
        .order_by(Pipeline.position.asc(), Pipeline.created_at.asc())
    )
    return list(result.scalars().all())


@router.post("", response_model=PipelineOut, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    body: PipelineCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Pipeline:
    branch = await db.get(Branch, body.branch_id)
    if branch is None or branch.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Branch no encontrada")

    # Position = max(existing) + 1
    max_pos_result = await db.execute(
        select(func.max(Pipeline.position)).where(
            Pipeline.branch_id == body.branch_id,
            Pipeline.tenant_id == current_user.tenant_id,
        )
    )
    max_pos = max_pos_result.scalar() or 0
    new_position = max_pos + 1

    pipeline = Pipeline(
        tenant_id=current_user.tenant_id,
        branch_id=body.branch_id,
        name=body.name,
        is_default=False,
        position=new_position,
    )
    db.add(pipeline)
    await db.flush()
    await db.refresh(pipeline)
    await db.commit()
    return pipeline


@router.patch("/{pipeline_id}", response_model=PipelineOut)
async def update_pipeline(
    pipeline_id: uuid.UUID,
    body: PipelineUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Pipeline:
    pipeline = await _get_pipeline_or_404(pipeline_id, current_user, db)

    if body.name is not None:
        pipeline.name = body.name
    if body.position is not None:
        pipeline.position = body.position

    await db.commit()
    await db.refresh(pipeline)
    return pipeline


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    pipeline_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    pipeline = await _get_pipeline_or_404(pipeline_id, current_user, db)

    # Guardia 1: debe quedar al menos un pipeline en la branch
    count_result = await db.execute(
        select(func.count()).where(
            Pipeline.branch_id == pipeline.branch_id,
            Pipeline.tenant_id == current_user.tenant_id,
        )
    )
    total_pipelines = count_result.scalar() or 0
    if total_pipelines <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar el único pipeline de la branch.",
        )

    # Guardia 2: sin deals activos en sus stages
    stages_result = await db.execute(
        select(PipelineStage.id).where(PipelineStage.pipeline_id == pipeline_id)
    )
    stage_ids = [r for r in stages_result.scalars().all()]

    if stage_ids:
        active_deals_result = await db.execute(
            select(func.count()).where(
                Deal.pipeline_stage_id.in_(stage_ids),
                Deal.is_won.is_(False),
                Deal.is_lost.is_(False),
            )
        )
        active_deals = active_deals_result.scalar() or 0
        if active_deals > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El pipeline tiene {active_deals} deal(s) activo(s). Muévelos antes de eliminarlo.",
            )

    # Si era el default, asigna is_default al pipeline con menor position restante
    if pipeline.is_default:
        next_default_result = await db.execute(
            select(Pipeline)
            .where(
                Pipeline.branch_id == pipeline.branch_id,
                Pipeline.tenant_id == current_user.tenant_id,
                Pipeline.id != pipeline_id,
            )
            .order_by(Pipeline.position.asc(), Pipeline.created_at.asc())
            .limit(1)
        )
        next_default = next_default_result.scalar_one_or_none()
        if next_default:
            next_default.is_default = True

    await db.delete(pipeline)
    await db.commit()
