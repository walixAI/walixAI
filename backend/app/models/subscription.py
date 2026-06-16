"""Subscription and FailedPayment models for Stripe billing (Sprint 10)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Subscription(Base):
    """Mirrors a Stripe Subscription object, one row per active/historical sub."""

    __tablename__ = "subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    stripe_price_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="trial")
    # Mirrors Stripe subscription.status: active / past_due / canceled / trialing
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="trialing")
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FailedPayment(Base):
    """Persists invoice.payment_failed events for monitoring in Platform dashboard."""

    __tablename__ = "failed_payments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stripe_invoice_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    amount_mxn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
