from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProductCategory(Base):
    """Product/service taxonomy for goal dimension filtering (not the same as ExpenseCategory)."""

    __tablename__ = "product_categories"

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_product_categories_tenant_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class MonthlyGoal(Base):
    """Sales target for a given month, optionally scoped to a dimension.

    dimension values: "global" | "deal_type" | "pipeline" | "product_category"
    dimension_value_text: used for deal_type (free string)
    dimension_value_uuid: used for pipeline_id or product_category_id

    NOTE — pipeline dimension resolution in walixAI:
    Deal has no pipeline_id column. To find deals that belong to a pipeline,
    join Deal → PipelineStage (via deal.pipeline_stage_id) → Pipeline
    (via PipelineStage.pipeline_id). This join is resolved in the run-rate
    logic (prompt 11), not here.

    NULL uniqueness note:
    The unique index below includes nullable columns. In Postgres, two NULLs are
    NOT considered equal in a regular unique index, so (tenant, year, month,
    "global", NULL, NULL) can theoretically be inserted twice. The application
    layer (prompt 9) must enforce the single-goal-per-dimension constraint,
    mirroring Lovable's COALESCE(…, '') approach but in Python.
    """

    __tablename__ = "monthly_goals"

    __table_args__ = (
        Index(
            "ix_monthly_goals_tenant_period_dimension",
            "tenant_id", "period_year", "period_month",
            "dimension", "dimension_value_text", "dimension_value_uuid",
            unique=True,
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"), server_default="0")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="MXN", server_default="MXN")
    # "global" | "deal_type" | "pipeline" | "product_category" — validated in Pydantic
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    dimension_value_text: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dimension_value_uuid: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class MonthlyGoalAssignment(Base):
    """Percentage-based share of a monthly goal assigned to a specific user."""

    __tablename__ = "monthly_goal_assignments"

    __table_args__ = (
        UniqueConstraint("goal_id", "user_id", name="uq_monthly_goal_assignments_goal_user"),
    )

    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monthly_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    share_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("0"), server_default="0")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"), server_default="0")


class MonthlyGoalHistory(Base):
    """Audit log for changes to monthly goals.

    goal_id and changed_by are stored without FK constraints so the history
    survives goal deletion (matching Lovable's design for this table).
    """

    __tablename__ = "monthly_goal_history"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # No FK — history must survive if the goal is deleted
    goal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    before_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # No FK — changed_by user may be deleted
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
