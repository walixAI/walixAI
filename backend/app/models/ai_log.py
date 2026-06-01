import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AICommandLog(Base):
    __tablename__ = "ai_command_logs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    intent_type: Mapped[str] = mapped_column(String(20), nullable=False)
    screen_context: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actions_taken: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
