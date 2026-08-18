import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlatformAIModelConfig(Base):
    """Modelo de Claude a usar por tier de tarea, configurable por platform_owner.

    Raíz del árbol, igual que Tenant — SIN tenant_id y SIN RLS a propósito
    (no pertenece a ningún tenant, es una decisión de plataforma completa).
    Ver migración r3s4t5u6v7w8 y app/core/ai_config.py::get_model_for_tier.
    """

    __tablename__ = "platform_ai_model_config"

    tier: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
