import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TenantPlan(str, enum.Enum):
    STARTER = "starter"
    GROWTH = "growth"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class AssignmentMode(str, enum.Enum):
    EQUITATIVA = "equitativa"
    POOL = "pool"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [e.value for e in enum_cls]


class Tenant(Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    plan: Mapped[TenantPlan] = mapped_column(
        Enum(
            TenantPlan,
            name="tenant_plan",
            values_callable=lambda x: _enum_values(TenantPlan),
        ),
        nullable=False,
        default=TenantPlan.STARTER,
    )
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    companies: Mapped[list["Company"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class Company(Base):
    __tablename__ = "companies"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="companies")
    branches: Mapped[list["Branch"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class Branch(Base):
    __tablename__ = "branches"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    wa_phone_number_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    # Encrypted at the application layer before storage.
    wa_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignment_mode: Mapped[AssignmentMode] = mapped_column(
        Enum(
            AssignmentMode,
            name="assignment_mode",
            values_callable=lambda x: _enum_values(AssignmentMode),
        ),
        nullable=False,
        default=AssignmentMode.EQUITATIVA,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    company: Mapped["Company"] = relationship(back_populates="branches")
