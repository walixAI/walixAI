"""Shared helper for inserting system-generated activities on leads."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.lead import Lead


async def create_system_activity(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID,
    description: str,
    db: AsyncSession,
) -> None:
    """Insert an Activity(type='system') and refresh the lead's last_activity_summary.

    Uses flush only — caller is responsible for commit.
    """
    db.add(
        Activity(
            lead_id=lead_id,
            tenant_id=tenant_id,
            activity_type="system",
            body=description[:1000],
            created_by=None,
        )
    )

    lead = await db.get(Lead, lead_id)
    if lead is not None:
        lead.last_activity_summary = description[:255]

    await db.flush()
