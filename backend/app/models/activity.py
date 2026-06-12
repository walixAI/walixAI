from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.lead import Lead


# ── System audit log (pre-Sprint 7) ──────────────────────────────────────────

class ActivityType(str, enum.Enum):
    HANDOFF = "handoff"
    ASSIGN = "assign"
    REPLY = "reply"
    RETURN_TO_BOT = "return_to_bot"
    STATUS_CHANGE = "status_change"
    STAGE_CHANGE = "stage_change"
    QUOTE = "quote"
    CALL = "call"
    TASK = "task"
    NOTE = "note"


class LeadActivity(Base):
    __tablename__ = "lead_activities"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activity_type: Mapped[ActivityType] = mapped_column(
        String(40), nullable=False, index=True
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


# ── Sprint 7 — CRM activity timeline ─────────────────────────────────────────
# User-facing activities: notes, tasks, calls, meetings, emails, system events.
# Distinct from lead_activities (system audit log above).
# Valid activity_type values enforced by DB CHECK ck_activities_activity_type.
ACTIVITY_TYPES = ("note", "task", "call", "meeting", "email", "system")


class Activity(Base):
    __tablename__ = "activities"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    activity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # DB column is "metadata"; that name is reserved by SQLAlchemy's DeclarativeBase.
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL when activity_type = 'system'
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    lead: Mapped[Lead] = relationship("Lead", back_populates="activities")
