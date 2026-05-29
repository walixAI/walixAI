import enum
import uuid
from typing import Any

from sqlalchemy import Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


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
