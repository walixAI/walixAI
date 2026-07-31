from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
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
    communication_style: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferred_message_length: Mapped[str | None] = mapped_column(String(20), nullable=True)


class AIDraftEdit(Base):
    """Records AI-suggested draft vs. what the user actually sent (Etapa 7.2).

    Used by aprendiz_agent.py (7.5) to learn per-tenant editing patterns.
    """

    __tablename__ = "ai_draft_edits"

    __table_args__ = (
        Index("ix_ai_draft_edits_tenant_user_created", "tenant_id", "user_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    original: Mapped[str] = mapped_column(Text, nullable=False)
    edited: Mapped[str] = mapped_column(Text, nullable=False)
    char_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class AIConversationMessage(Base):
    """One turn in a Copiloto conversational session.

    session_id is the conversationKey from the frontend (e.g. "global",
    "contact:uuid", "deal:uuid"). role is user/assistant/tool — validated
    in Pydantic, not with a DB CHECK constraint.
    """

    __tablename__ = "ai_conversation_history"

    __table_args__ = (
        Index("ix_ai_conv_history_session_created", "session_id", "created_at"),
        Index("ix_ai_conv_history_tenant_id", "tenant_id"),
        Index("ix_ai_conv_history_user_id", "user_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )


class CopilotCapability(Base):
    """B1 — Walix Builder: receta o capacidad nativa del Copiloto.

    kind="recipe"  → pasos encadenados definidos en recipe_json (ejecutados por el motor B3).
    kind="native"  → reservado para primitivas built-in del motor.
    scope_roles almacena valores del UserRole real de walixAI en minúsculas
    (ej. "gerente", "asesor") — NO los nombres del Lovable repo.
    Todos los campos de listas usan JSONB (patrón universal del proyecto).
    """

    __tablename__ = "copilot_capabilities"

    __table_args__ = (
        CheckConstraint("kind IN ('recipe', 'native')", name="ck_copilot_cap_kind"),
        CheckConstraint("scope_type IN ('all', 'role', 'user')", name="ck_copilot_cap_scope_type"),
        Index("ix_copilot_capabilities_tenant_active", "tenant_id", "is_active"),
        Index("ix_copilot_capabilities_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "recipe" | "native"
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="recipe", server_default="recipe"
    )
    recipe_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="'{}'"
    )
    # Frases que pueden disparar esta receta
    trigger_phrases: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'"
    )
    # "all" | "role" | "user"
    scope_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="all", server_default="all"
    )
    # UserRole values in lowercase: ["gerente", "asesor", ...]
    scope_roles: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'"
    )
    # UUIDs of specific users with access
    scope_user_ids: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'"
    )
    # ["web"] | ["whatsapp"] | ["web", "whatsapp"]
    channels: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=lambda: ["web"], server_default='\'["web"]\''
    )
    require_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class CopilotActionLog(Base):
    """B1 — Bitácora de ejecución de pasos de una receta del Copiloto.

    Append-only en la práctica, pero incluye updated_at porque Base lo exige
    en todos los modelos del proyecto.
    status: "ok" | "error" | "dry_run"
    """

    __tablename__ = "copilot_action_log"

    __table_args__ = (
        CheckConstraint("status IN ('ok', 'error', 'dry_run')", name="ck_copilot_log_status"),
        Index("ix_copilot_action_log_tenant_created", "tenant_id", "created_at"),
        Index("ix_copilot_action_log_capability_id", "capability_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    capability_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("copilot_capabilities.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # "ok" | "error" | "dry_run"
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ok", server_default="ok"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
