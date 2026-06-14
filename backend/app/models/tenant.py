from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    pass

_ONBOARDING_STATUS_VALUES = ["pending", "draft", "approved", "active"]


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

    # ── Sprint 8B: Industry Templates ─────────────────────────────────────────
    industry_key: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="generico"
    )
    industry_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_name: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="Contacto"
    )
    entity_plural: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="Contactos"
    )
    contact_statuses_config: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    onboarding_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    companies: Mapped[list["Company"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def get_industry_template(self) -> dict:
        """Retorna el template de la industria activa del tenant."""
        from app.industry_templates.catalog import get_template
        return get_template(self.industry_key)

    def get_entity_display(self, plural: bool = False) -> str:
        """Retorna el nombre de la entidad (singular o plural) para este tenant."""
        return self.entity_plural if plural else self.entity_name


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

    # Sprint 4 — AI config & onboarding
    ai_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(30), nullable=True)
    onboarding_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    bot_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    business_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship(back_populates="branches")
