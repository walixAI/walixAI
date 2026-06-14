"""Shared helpers for inserting system-generated activities on leads."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.lead import Lead

_FIELD_LABELS: dict[str, str] = {
    "name": "Nombre",
    "last_name": "Apellido",
    "wa_phone": "Teléfono",
    "contact_phone": "Teléfono",
    "company": "Empresa",
    "status": "Estatus",
    "prospection_source": "Fuente",
    "assigned_to": "Vendedor asignado",
}


async def create_system_activity(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID,
    description: str,
    db: AsyncSession,
    *,
    metadata: dict[str, Any] | None = None,
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
            extra_data=metadata,
            created_by=None,
        )
    )

    lead = await db.get(Lead, lead_id)
    if lead is not None:
        lead.last_activity_summary = description[:255]

    await db.flush()


async def create_field_change_activity(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID,
    changed_by_id: uuid.UUID,
    changed_by_name: str,
    changes: dict[str, tuple[Any, Any]],
    db: AsyncSession,
) -> None:
    """Create one system activity per changed field.

    Skips fields where old == new. Uses flush only — caller commits.
    """
    for field, (old_val, new_val) in changes.items():
        if old_val == new_val:
            continue
        label = _FIELD_LABELS.get(field, field)
        old_str = str(old_val) if old_val is not None else "(vacío)"
        new_str = str(new_val) if new_val is not None else "(vacío)"
        body = f"{label} cambiado: {old_str} → {new_str}"
        await create_system_activity(
            lead_id=lead_id,
            tenant_id=tenant_id,
            description=body,
            metadata={
                "field": field,
                "old_value": str(old_val) if old_val is not None else None,
                "new_value": str(new_val) if new_val is not None else None,
                "changed_by_id": str(changed_by_id),
                "changed_by_name": changed_by_name,
            },
            db=db,
        )
