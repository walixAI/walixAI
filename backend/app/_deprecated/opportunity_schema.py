from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


# ── Nested light schemas ──────────────────────────────────────────────────────

class LeadMinimal(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None = None
    last_name: str | None = None
    wa_phone: str | None = None
    company: str | None = None


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    color: str | None = None
    order_index: int
    is_won: bool
    is_lost: bool
    probability_default: int | None = None


# ── Opportunity CRUD schemas ──────────────────────────────────────────────────

class OpportunityCreate(BaseModel):
    title: str
    lead_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None
    amount: Decimal | None = None
    currency: str = "MXN"
    probability: int | None = None
    close_date: date | None = None
    source: str | None = None
    notes: str | None = None

    @field_validator("probability")
    @classmethod
    def clamp_probability(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("probability must be 0-100")
        return v

    @field_validator("currency")
    @classmethod
    def upper_currency(cls, v: str) -> str:
        return v.upper()


class OpportunityUpdate(BaseModel):
    title: str | None = None
    lead_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None
    amount: Decimal | None = None
    currency: str | None = None
    probability: int | None = None
    close_date: date | None = None
    source: str | None = None
    notes: str | None = None
    ai_suggestion: str | None = None
    ai_suggestion_urgency: str | None = None
    urgency_score: int | None = None

    @field_validator("probability", "urgency_score", mode="before")
    @classmethod
    def clamp_0_100(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("value must be 0-100")
        return v

    @field_validator("currency", mode="before")
    @classmethod
    def upper_currency(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    title: str
    amount: Decimal | None = None
    currency: str
    probability: int | None = None
    close_date: date | None = None
    source: str | None = None
    status: str
    won_at: datetime | None = None
    lost_at: datetime | None = None
    lost_reason: str | None = None
    stage_entered_at: datetime
    last_activity_at: datetime | None = None
    ai_suggestion: str | None = None
    ai_suggestion_urgency: str | None = None
    urgency_score: int | None = None
    notes: str | None = None
    assigned_to: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    # Nested
    lead: LeadMinimal | None = None
    stage: StageRead | None = None


# ── Stage move ────────────────────────────────────────────────────────────────

class OpportunityMove(BaseModel):
    stage_id: uuid.UUID
    moved_by: str = "manual"  # manual | ai_command | auto

    @field_validator("moved_by")
    @classmethod
    def validate_moved_by(cls, v: str) -> str:
        if v not in ("manual", "ai_command", "auto"):
            return "manual"
        return v


# ── Mark lost ─────────────────────────────────────────────────────────────────

class OpportunityMarkLost(BaseModel):
    lost_reason: str | None = None
    reason_code: str | None = None  # price | competitor | timing | no_budget | other


# ── Board (kanban) ────────────────────────────────────────────────────────────

class OpportunityCard(BaseModel):
    """Light card for kanban — avoids serializing full lead/stage on every card."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    amount: Decimal | None = None
    currency: str
    probability: int | None = None
    close_date: date | None = None
    status: str
    stage_entered_at: datetime
    last_activity_at: datetime | None = None
    ai_suggestion: str | None = None
    ai_suggestion_urgency: str | None = None
    urgency_score: int | None = None
    assigned_to: uuid.UUID | None = None
    assigned_to_name: str | None = None
    lead_name: str | None = None
    lead_wa_phone: str | None = None
    days_in_stage: int = 0


class BoardStage(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    color: str | None = None
    order_index: int
    is_won: bool
    is_lost: bool
    probability_default: int | None = None
    opportunities: list[OpportunityCard]
    total: int
    total_amount: Decimal


class BoardRead(BaseModel):
    stages: list[BoardStage]
    currency: str = "MXN"


# ── Forecast ──────────────────────────────────────────────────────────────────

class ForecastStage(BaseModel):
    stage_id: uuid.UUID
    stage_name: str
    stage_color: str | None = None
    count: int
    total_amount: Decimal
    weighted_amount: Decimal  # sum(amount * probability / 100)


class ForecastRead(BaseModel):
    stages: list[ForecastStage]
    total_pipeline: Decimal     # suma cruda de montos abiertos
    total_weighted: Decimal     # suma ponderada
    currency: str = "MXN"
