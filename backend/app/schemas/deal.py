from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_LOST_REASONS = frozenset({"price", "timing", "competition", "no_response", "other"})


class DealCreate(BaseModel):
    lead_id: uuid.UUID
    pipeline_stage_id: uuid.UUID
    title: str
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    probability: int = Field(default=0, ge=0, le=100)
    expected_close_date: date | None = None
    source: str | None = None
    notes: str | None = None
    owner_id: uuid.UUID | None = None


class DealUpdate(BaseModel):
    pipeline_stage_id: uuid.UUID | None = None
    title: str | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None
    is_won: bool | None = None
    is_lost: bool | None = None
    source: str | None = None
    notes: str | None = None
    lost_reason: str | None = None
    lost_comment: str | None = None
    owner_id: uuid.UUID | None = None

    @field_validator("lost_reason")
    @classmethod
    def validate_lost_reason(cls, v: str | None) -> str | None:
        if v is not None and v not in _LOST_REASONS:
            raise ValueError(f"lost_reason debe ser uno de: {', '.join(sorted(_LOST_REASONS))}")
        return v

    @field_validator("lost_comment")
    @classmethod
    def validate_lost_comment(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 500:
            raise ValueError("lost_comment no puede superar 500 caracteres")
        return v


class DealRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    lead_id: uuid.UUID
    pipeline_stage_id: uuid.UUID
    title: str
    amount: Decimal
    probability: int
    expected_close_date: date | None
    is_won: bool
    is_lost: bool
    source: str | None
    notes: str | None
    lost_reason: str | None
    lost_comment: str | None
    owner_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DealListResponse(BaseModel):
    items: list[DealRead]
    total: int
    page: int
    page_size: int
