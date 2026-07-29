"""DEPRECADO (ver Etapa 3 del plan de migración) — sin consumidor activo desde 2026-07-28.
No se elimina la tabla sin aprobación explícita, dado que aún existen datos históricos.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Valid type values (enforced at app level, not via DB enum to avoid ALTER TYPE migrations)
OPPORTUNITY_ACTIVITY_TYPES = (
    "created",
    "stage_change",
    "note",
    "task",
    "message",
    "ai_suggestion",
    "won",
    "lost",
)


class OpportunityActivity(Base):
    """Timeline of events attached to an opportunity (user-facing and system)."""

    __tablename__ = "opportunity_activities"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # created | stage_change | note | task | message | ai_suggestion | won | lost
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # created_at inherited from Base
