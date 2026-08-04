import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DashboardWidget(Base):
    """Global catalog of available dashboard widgets (not per-tenant)."""
    __tablename__ = "dashboard_widgets"

    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    native_key: Mapped[str] = mapped_column(String(100), nullable=False)
    min_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    surface: Mapped[str] = mapped_column(String(50), nullable=False, default="dashboard")


class DashboardLayout(Base):
    """Saved layout for a tenant+scope combination.

    scope format:
      "tenant_default"           — baseline for all users in this tenant
      "role:<UserRole.value>"    — override for a specific role
      "user:<uuid>"              — personal override for a specific user
    """
    __tablename__ = "dashboard_layouts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scope", name="uq_dashboard_layouts_tenant_scope"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
