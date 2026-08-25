from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    pass

_ONBOARDING_STATUS_VALUES = ["pending", "draft", "approved", "active"]


class TenantPlan(str, enum.Enum):
    TRIAL = "trial"       # 14-day free trial (Sprint 9)
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
    deal_name: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="Oportunidad"
    )
    deal_plural: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="Oportunidades"
    )
    contact_statuses_config: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    onboarding_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Sprint 9: Trial & Registration ────────────────────────────────────────
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    registration_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    referral_source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Sprint 11: ROI Dashboard ───────────────────────────────────────────────
    roi_revenue_per_conversion: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    # ── Sprint 12: Bot config desde onboarding ────────────────────────────────
    onboarding_extracted_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    # ── Metas / Finanzas ──────────────────────────────────────────────────────
    deal_type_options: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default='["Venta", "Servicio"]'
    )
    finance_scope: Mapped[str] = mapped_column(
        String(10), nullable=False, default="branch", server_default="branch"
    )
    monthly_goal_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    monthly_goal_by_type: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    count_business_days: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    profit_thresholds: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        default=lambda: {"green": 20, "yellow": 10, "orange": 0},
        server_default='{"green": 20, "yellow": 10, "orange": 0}',
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

    def get_deal_display(self, plural: bool = False) -> str:
        """Retorna el nombre del deal (singular o plural) para este tenant."""
        return self.deal_plural if plural else self.deal_name


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

    # ── Sprint 12: Bot config generada desde onboarding ───────────────────────
    bot_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    bot_tone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bot_qualification_questions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    bot_config_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    bot_config_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Prompt Utel #2 — mensaje de bienvenida por branch para leads de Meta/Google
    # Ads (placeholder {name}). None -> fallback genérico, ver
    # app/api/webhooks.py::_build_ad_lead_welcome_message.
    ad_lead_welcome_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Metas / Finanzas ──────────────────────────────────────────────────────
    monthly_goal_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    monthly_goal_by_type: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    company: Mapped["Company"] = relationship(back_populates="branches")
