from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIEntityContext(Base):
    """Rolling AI memory for a specific entity (contact, deal, conversation, team)."""

    __tablename__ = "ai_entity_context"

    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "entity_id", name="uq_ai_entity_context_tenant_type_entity"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # "contact" | "deal" | "conversation" | "team"
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # No FK — entity may live in different tables depending on entity_type
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    context_summary: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    key_facts: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    last_interaction: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sentiment: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown", server_default="unknown")
    urgency_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class AIMemoryEvent(Base):
    """Immutable log of AI-relevant events for an entity."""

    __tablename__ = "ai_memory_events"

    __table_args__ = (
        Index("ix_ai_memory_events_tenant_entity_created", "tenant_id", "entity_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class AIOutcomeFeedback(Base):
    """Records the measured outcome of an AI agent suggestion for feedback loops (Etapa 6.3)."""

    __tablename__ = "ai_outcome_feedback"

    __table_args__ = (
        Index("ix_ai_outcome_feedback_tenant_created", "tenant_id", "created_at"),
        Index("ix_ai_outcome_feedback_tenant_outcome", "tenant_id", "outcome"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    suggestion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_suggestions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action_taken: Mapped[str] = mapped_column(String(50), nullable=False)
    # No FK — entity may live in different tables depending on entity_type
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    outcome_value: Mapped[float] = mapped_column(
        Numeric, nullable=False, default=0, server_default="0"
    )
    days_to_outcome: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_at_action: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )


class AITenantPattern(Base):
    """Aggregated business patterns learned from AIOutcomeFeedback for a tenant (Etapa 6.4)."""

    __tablename__ = "ai_tenant_patterns"

    __table_args__ = (
        UniqueConstraint("tenant_id", "pattern_type", name="uq_ai_tenant_patterns_tenant_type"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "best_followup_day" | "peak_response_hours" | "avg_close_days" | "top_objections"
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False)
    pattern_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    confidence_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class AIUserProfile(Base):
    """Per-user closing statistics derived from Deal data (Etapa 6.5).

    Fields requiring AI-drafted message data (communication_style,
    preferred_message_length) are intentionally omitted — that feature
    is not yet available in Walix.
    """

    __tablename__ = "ai_user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_deals_closed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_deals_lost: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    close_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    best_close_day: Mapped[str | None] = mapped_column(String(20), nullable=True)
    best_close_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_performing_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
