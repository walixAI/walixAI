from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SavedViewCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    filters: dict = Field(default_factory=dict)
    view_mode: Literal["list", "kanban", "cards"] = "list"
    is_default: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class SavedViewUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    filters: dict | None = None
    view_mode: Literal["list", "kanban", "cards"] | None = None
    is_default: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class SavedViewRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    filters: dict
    view_mode: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
