from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OnboardingConversation(Base):
    """Un turno de la conversación de onboarding donde el usuario describe su negocio.

    El sistema usa estos turnos para inferir la industria y configurar el tenant
    automáticamente vía IA durante el flujo de onboarding conversacional.
    """

    __tablename__ = "onboarding_conversations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    turn: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    inferred_industry: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    follow_up_questions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
