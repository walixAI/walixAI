from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FinancePermission(Base):
    """Grants a user access to financial reports for a tenant or branch.

    branch_id=NULL  → tenant-wide access (owner-level)
    branch_id=<id>  → scoped to that branch only
    """

    __tablename__ = "finance_permissions"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "branch_id", "user_id",
            name="uq_finance_permissions_tenant_branch_user",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ExpenseCategory(Base):
    """Shared catalog of expense categories at tenant level."""

    __tablename__ = "expense_categories"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # "fijo" | "variable"
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class RecurringExpense(Base):
    """Template that generates periodic expenses (e.g. monthly rent)."""

    __tablename__ = "recurring_expenses"

    __table_args__ = (
        Index(
            "ix_recurring_expenses_tenant", "tenant_id",
            postgresql_where=sa_text("is_active = true"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expense_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    day_of_month: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class ExpenseRule(Base):
    """Rule that auto-generates an expense when a deal closes (e.g. commission %)."""

    __tablename__ = "expense_rules"

    __table_args__ = (
        Index(
            "ix_expense_rules_tenant", "tenant_id",
            postgresql_where=sa_text("is_active = true"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expense_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # "percent_of_deal" | "fixed_per_deal" | "percent_of_cost"
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    deal_type_filter: Mapped[str | None] = mapped_column(String(20), nullable=True)
    auto_confirm: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class Expense(Base):
    """Individual expense record, scoped to tenant or branch per finance_scope."""

    __tablename__ = "expenses"

    __table_args__ = (
        Index("ix_expenses_tenant_incurred_at", "tenant_id", "incurred_at"),
        Index("ix_expenses_branch_incurred_at", "branch_id", "incurred_at"),
        Index("ix_expenses_status", "tenant_id", "status"),
        Index("ix_expenses_recurring", "recurring_id", "incurred_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expense_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="MXN", server_default="MXN"
    )
    incurred_at: Mapped[date] = mapped_column(
        Date, nullable=False, default=date.today, server_default="CURRENT_DATE"
    )
    # "draft" | "confirmed"
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="confirmed", server_default="confirmed"
    )
    # "manual" | "recurring" | "rule" | "whatsapp"
    source: Mapped[str] = mapped_column(
        String(10), nullable=False, default="manual", server_default="manual"
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expense_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    recurring_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recurring_expenses.id", ondelete="SET NULL"),
        nullable=True,
    )
    receipt_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
