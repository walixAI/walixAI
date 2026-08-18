import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AITokenUsage(Base):
    """Registro de consumo de tokens de Claude, por tenant.

    Tabla de tenant normal — CON RLS estándar (4 policies), a diferencia de
    platform_ai_model_config (raíz, sin RLS). Ver migración s4t5u6v7w8x9,
    fn_aggregate_token_usage_platform, y
    app/core/token_tracking.py::log_token_usage.
    """

    __tablename__ = "ai_token_usage"

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
    # Nullable: algunos usos son de agentes automáticos (Celery beat), no de
    # un usuario interactuando en una sesión de chat.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # ej. "copilot_chat", "follow_up_agent", "pipeline_agent" — qué generó el consumo.
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)

    # Override del created_at heredado de Base: la migración s4t5u6v7w8x9
    # crea ix_ai_token_usage_created_at explícitamente (consultas del
    # dashboard de Fase 7 filtran por rango de fechas) — sin este
    # index=True, --autogenerate ve el índice real en la DB pero no en los
    # metadatos del modelo y propone borrarlo como drift.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
