import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

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
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    schedule_hour: Mapped[int] = mapped_column(
        Integer, nullable=False, default=9, server_default="9"
    )
    silence_start: Mapped[int] = mapped_column(
        Integer, nullable=False, default=21, server_default="21"
    )
    silence_end: Mapped[int] = mapped_column(
        Integer, nullable=False, default=8, server_default="8"
    )
    threshold_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, default=48, server_default="48"
    )
