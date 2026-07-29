from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Pipeline(Base):
    __tablename__ = "pipelines"
    __table_args__ = (
        UniqueConstraint("branch_id", "name", name="uq_pipelines_branch_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


async def resolve_default_pipeline_id(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    *,
    user_branch_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Returns the pipeline_id of the is_default pipeline for the tenant.

    Branch resolution order:
    1. user_branch_id if provided (non-owner users with an assigned branch).
    2. First active branch of the tenant by created_at (owner / multi-branch fallback).

    Returns None if no branch or no default pipeline is found.
    Replicates the branch-resolution pattern from PipelineStage.create_from_template().
    """
    from app.models.tenant import Branch

    if user_branch_id is not None:
        resolved_branch_id = user_branch_id
    else:
        resolved_branch_id = (
            await db.execute(
                select(Branch.id)
                .where(Branch.tenant_id == tenant_id, Branch.is_active.is_(True))
                .order_by(Branch.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()

    if resolved_branch_id is None:
        return None

    return (
        await db.execute(
            select(Pipeline.id)
            .where(Pipeline.branch_id == resolved_branch_id, Pipeline.is_default.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
