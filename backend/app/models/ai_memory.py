from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
