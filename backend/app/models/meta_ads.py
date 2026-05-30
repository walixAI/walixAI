import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetaLeadConfig(Base):
    __tablename__ = "meta_lead_configs"

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
    page_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    form_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # Encrypted at the application layer before storage.
    page_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    field_mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
