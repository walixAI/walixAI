from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.activity import ACTIVITY_TYPES, CLOSED_VIA_VALUES, TASK_KINDS


class ActivityCreate(BaseModel):
    activity_type: str
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, min_length=2, max_length=500)
    extra_data: dict | None = None
    due_date: datetime | None = None
    completed_at: datetime | None = None
    # ── Etapa 5 task extensions ──────────────────────────────────────────────
    task_kind: str | None = None
    assignee_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    closed_via: str | None = None
    closed_note: str | None = None

    @field_validator("activity_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ACTIVITY_TYPES:
            raise ValueError(f"activity_type must be one of {ACTIVITY_TYPES}")
        return v

    @field_validator("task_kind")
    @classmethod
    def validate_task_kind(cls, v: str | None) -> str | None:
        if v is not None and v not in TASK_KINDS:
            raise ValueError(f"task_kind must be one of {TASK_KINDS}")
        return v

    @field_validator("closed_via")
    @classmethod
    def validate_closed_via(cls, v: str | None) -> str | None:
        if v is not None and v not in CLOSED_VIA_VALUES:
            raise ValueError(f"closed_via must be one of {CLOSED_VIA_VALUES}")
        return v


class ActivityRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    activity_type: str
    title: str | None = None
    body: str | None = None
    extra_data: dict | None = None
    due_date: datetime | None = None
    completed_at: datetime | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    # ── Etapa 5 task extensions ──────────────────────────────────────────────
    task_kind: str | None = None
    assignee_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    closed_via: str | None = None
    closed_note: str | None = None
