from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.tag import lead_tags_table

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.tag import Tag

# ── Soft-delete convention ────────────────────────────────────────────────────
# Lead uses soft delete via `deleted_at` (TIMESTAMPTZ, nullable).
# NULL  → active record.
# Non-NULL → deleted; the row is retained for audit/history.
#
# EVERY query that returns leads to users MUST include:
#     .where(Lead.deleted_at.is_(None))
# Failure to add this filter will expose deleted contacts in the UI.


class LeadStatus(str, enum.Enum):
    NUEVO = "nuevo"
    EN_CALIFICACION = "en_calificacion"
    CALIFICADO = "calificado"
    ESCALADO = "escalado"
    PERDIDO = "perdido"


class LeadSentiment(str, enum.Enum):
    NEUTRAL = "neutral"
    INTERESADO = "interesado"
    URGENTE = "urgente"
    NEGATIVO = "negativo"


class LeadSource(str, enum.Enum):
    WHATSAPP_INBOUND = "whatsapp_inbound"
    META_ADS = "meta_ads"
    MANUAL = "manual"


class Lead(Base):
    __tablename__ = "leads"

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
    wa_phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Sprint 7 — Contacts module
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    prospection_source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="manual", server_default="manual"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_activity_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        Enum(
            LeadStatus,
            name="lead_status",
            values_callable=lambda x: [e.value for e in LeadStatus],
        ),
        nullable=False,
        default=LeadStatus.NUEVO,
    )
    qualification_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    sentiment: Mapped[LeadSentiment] = mapped_column(
        Enum(
            LeadSentiment,
            name="lead_sentiment",
            values_callable=lambda x: [e.value for e in LeadSentiment],
        ),
        nullable=False,
        default=LeadSentiment.NEUTRAL,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[LeadSource] = mapped_column(
        Enum(
            LeadSource,
            name="lead_source",
            values_callable=lambda x: [e.value for e in LeadSource],
        ),
        nullable=False,
        default=LeadSource.WHATSAPP_INBOUND,
    )
    last_rag_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    qualification_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    qualification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Sprint 3: handoff tracking
    handoff_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    handoff_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Sprint 3: Meta Lead Ads origin
    meta_lead_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    meta_form_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    meta_ad_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Sprint 4: dynamic pipeline
    pipeline_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_stages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Sprint 5: proactive alerts
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_alert_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Sprint 6: prediction score
    current_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # up | down | flat
    current_score_trend: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # Sprint 7: Contacts module relationships
    activities: Mapped[list[Activity]] = relationship(
        "Activity",
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="Activity.created_at.desc()",
        lazy="select",
    )
    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        secondary=lead_tags_table,
        lazy="select",
    )
