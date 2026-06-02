import enum
import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


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
