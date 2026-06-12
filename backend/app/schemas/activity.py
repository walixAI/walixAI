from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.activity import ACTIVITY_TYPES


class ActivityCreate(BaseModel):
    activity_type: str
    title: str | None = None
    body: str | None = None
    extra_data: dict | None = None
    due_date: datetime | None = None
    completed_at: datetime | None = None

    @field_validator("activity_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ACTIVITY_TYPES:
            raise ValueError(f"activity_type must be one of {ACTIVITY_TYPES}")
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
