import uuid
from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, Integer, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailyMetric(Base):
    __tablename__ = "daily_metrics"
    __table_args__ = (
        UniqueConstraint("branch_id", "metric_date", name="uq_daily_metrics_branch_date"),
    )

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
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Lead funnel
    leads_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    leads_qualified: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    leads_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    leads_lost: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Messaging
    messages_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    messages_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Activities
    calls_logged: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tasks_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    quotes_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Response time
    avg_first_response_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Per-agent breakdown {user_id: {leads_created: N, ...}}
    metrics_by_agent: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )


class SentimentSnapshot(Base):
    __tablename__ = "sentiment_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "branch_id", "snapshot_date", name="uq_sentiment_snapshots_branch_date"
        ),
    )

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
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Weighted average sentiment (0.0=negative … 1.0=positive)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)

    # {neutral: N, interesado: N, urgente: N, negativo: N}
    distribution: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    # {stage_id: score, ...}
    by_stage: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    # {user_id: score, ...}
    by_agent: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
