import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tag(Base):
    __tablename__ = "tags"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # UNIQUE (tenant_id, name) enforced by uq_tags_tenant_name
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # Hex color #RRGGBB; auto-assigned by service layer if null on creation
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)


# ── lead_tags pivot ──────────────────────────────────────────────────────────
# Defined as a plain Table (not a Base subclass) because it has a composite
# PK and no surrogate UUID — standard SQLAlchemy many-to-many pattern.

from sqlalchemy import Column, Table  # noqa: E402

lead_tags_table = Table(
    "lead_tags",
    Base.metadata,
    Column(
        "lead_id",
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
)
