from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class TagRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str | None = None


class UserMinimal(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str


class ContactCreate(BaseModel):
    wa_phone: str
    name: str | None = None
    last_name: str | None = None
    company: str | None = None
    prospection_source: str = "manual"
    pipeline_stage_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] = []

    @field_validator("wa_phone")
    @classmethod
    def phone_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("wa_phone is required")
        return v


class ContactUpdate(BaseModel):
    name: str | None = None
    last_name: str | None = None
    company: str | None = None
    prospection_source: str | None = None
    pipeline_stage_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] | None = None
    status: str | None = None
    assigned_to: uuid.UUID | None = None


class ContactRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    wa_phone: str
    name: str | None = None
    last_name: str | None = None
    company: str | None = None
    prospection_source: str
    deleted_at: datetime | None = None
    last_activity_summary: str | None = None
    pipeline_stage_id: uuid.UUID | None = None
    status: str | None = None
    current_score: int | None = None
    current_score_trend: str | None = None
    created_at: datetime
    updated_at: datetime
    tags: list[TagRow] = []
    assigned_user: UserMinimal | None = None


class ContactListResponse(BaseModel):
    items: list[ContactRow]
    total: int
    page: int
    page_size: int
