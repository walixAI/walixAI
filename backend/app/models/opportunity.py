"""DEPRECADO (ver Etapa 3 del plan de migración) — sin consumidor activo desde 2026-07-28.
No se elimina la tabla sin aprobación explícita, dado que aún existen datos históricos.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DATE,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.pipeline import PipelineStage


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opp_tenant_branch_stage", "tenant_id", "branch_id", "stage_id"),
        Index("ix_opp_tenant_status", "tenant_id", "status"),
        Index("ix_opp_tenant_close_date", "tenant_id", "close_date"),
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
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_stages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="MXN", server_default="MXN"
    )
    # 0-100; puede diferir del probability_default de la etapa si el usuario lo ajusta
    probability: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    close_date: Mapped[date | None] = mapped_column(DATE, nullable=True)
    # whatsapp | web_form | referral | manual
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # open | won | lost
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="open", server_default="open"
    )
    won_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lost_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Para calcular "días en etapa" en el kanban sin necesitar historial
    stage_entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    # Para badges de salud (Stale, Hot, etc.)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # IA — sugerencia de siguiente acción
    ai_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # high | medium | low
    ai_suggestion_urgency: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    # 0-100; para el punto rojo pulsante en tarjetas de alto riesgo
    urgency_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # ── Relaciones ligeras (lazy=select para no cargar siempre) ───────────────
    lead: Mapped[Lead | None] = relationship(
        "Lead", foreign_keys=[lead_id], lazy="select"
    )
    stage: Mapped[PipelineStage | None] = relationship(
        "PipelineStage", foreign_keys=[stage_id], lazy="select"
    )
