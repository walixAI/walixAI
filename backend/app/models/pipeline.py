from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

if TYPE_CHECKING:
    pass


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("branch_id", "slug", name="uq_pipeline_stages_branch_slug"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_won: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_advance_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Sprint 8B: Industry Templates ─────────────────────────────────────────
    stage_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str] = mapped_column(
        String(7), nullable=False, server_default="#6B7280"
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # ── Pipeline (Oportunidades / Deals) ─────────────────────────────────────
    probability_default: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )  # 0-100; sugerido al crear deal/oportunidad en esta etapa

    # ── Class helpers ──────────────────────────────────────────────────────────

    @classmethod
    async def create_from_template(
        cls,
        tenant_id: uuid.UUID,
        stages: list[dict],
        db: AsyncSession,
        *,
        branch_id: uuid.UUID | None = None,
    ) -> int:
        """Crea etapas de pipeline desde un template de industria.

        Si branch_id es None, usa la primera branch activa del tenant.
        Retorna el número de stages creadas.
        """
        from app.models.tenant import Branch

        if branch_id is None:
            result = await db.execute(
                select(Branch.id)
                .where(Branch.tenant_id == tenant_id, Branch.is_active.is_(True))
                .order_by(Branch.created_at.asc())
                .limit(1)
            )
            branch_id = result.scalar_one_or_none()
            if branch_id is None:
                return 0

        created = 0
        for stage in stages:
            db.add(cls(
                tenant_id=tenant_id,
                branch_id=branch_id,
                name=stage["label"],
                slug=stage["key"],
                stage_key=stage["key"],
                order_index=stage["order"],
                color=stage.get("color", "#6B7280"),
                is_won=stage["key"] in ("closed_won", "discharged", "delivered", "graduated"),
                is_lost=stage["key"] == "lost",
                is_archived=False,
            ))
            created += 1

        await db.flush()
        return created
