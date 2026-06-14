"""Contact CRUD executor — called by the WalixAIBar command interpreter."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.user import User

logger = logging.getLogger(__name__)

_NOPHONE = "NOPHONE_"

_ACTIVITY_EMOJIS: dict[str, str] = {
    "note": "📝", "call": "📞", "meeting": "📅",
    "task": "✅", "email": "📧",
}


def _normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    p = raw.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not p:
        return None
    if not p.startswith("+"):
        if len(p) == 10:
            p = "+52" + p
        elif len(p) == 12 and p.startswith("52"):
            p = "+" + p
        else:
            p = "+52" + p
    return p


def _lead_dict(lead: Lead) -> dict[str, Any]:
    phone = lead.wa_phone if not (lead.wa_phone or "").startswith(_NOPHONE) else None
    return {
        "id": str(lead.id),
        "name": lead.name,
        "lastName": lead.last_name,
        "company": lead.company,
        "phone": phone,
        "status": lead.status.value if hasattr(lead.status, "value") else str(lead.status),
    }


async def _find_leads(
    contact_ref: str, tenant_id: uuid.UUID, db: AsyncSession
) -> list[Lead]:
    term = f"%{contact_ref.strip()}%"
    result = await db.execute(
        select(Lead)
        .where(
            Lead.tenant_id == tenant_id,
            Lead.deleted_at.is_(None),
            or_(
                Lead.name.ilike(term),
                Lead.last_name.ilike(term),
                Lead.wa_phone.ilike(term),
            ),
        )
        .limit(5)
    )
    return list(result.scalars().all())


# ── 1. contact_create ─────────────────────────────────────────────────────────

async def execute_contact_create(
    params: dict[str, Any], user: User, db: AsyncSession
) -> dict:
    name = str(params.get("name", "")).strip()
    if not name:
        return {"action": "error", "message": "Se requiere el nombre del contacto"}

    phone = _normalize_phone(params.get("phone"))
    wa_phone = phone or f"{_NOPHONE}{uuid.uuid4().hex[:16].upper()}"

    lead = Lead(
        branch_id=user.branch_id,
        tenant_id=user.tenant_id,
        wa_phone=wa_phone,
        name=name,
        last_name=params.get("last_name") or None,
        company=params.get("company") or None,
        prospection_source=params.get("prospection_source", "manual"),
        status=LeadStatus.NUEVO,
        source=LeadSource.MANUAL,
        sentiment=LeadSentiment.NEUTRAL,
        assigned_to=user.id,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    return {
        "action": "contact_created",
        "contact": _lead_dict(lead),
        "message": f"Contacto {name} creado correctamente",
    }


# ── 2. contact_read ───────────────────────────────────────────────────────────

async def execute_contact_read(
    params: dict[str, Any], user: User, db: AsyncSession
) -> dict:
    base = select(Lead).where(Lead.tenant_id == user.tenant_id, Lead.deleted_at.is_(None))

    q = (params.get("q") or "").strip()
    if q:
        term = f"%{q}%"
        base = base.where(
            or_(
                Lead.name.ilike(term), Lead.last_name.ilike(term),
                Lead.company.ilike(term), Lead.wa_phone.ilike(term),
            )
        )

    status_val = params.get("status")
    if status_val:
        statuses = [status_val] if isinstance(status_val, str) else list(status_val)
        base = base.where(Lead.status.in_(statuses))

    company = (params.get("company") or "").strip()
    if company:
        base = base.where(Lead.company.ilike(f"%{company}%"))

    date_range = params.get("date_range")
    if date_range:
        now = datetime.now(timezone.utc)
        if date_range == "today":
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "this_week":
            cutoff = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "this_month":
            cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            cutoff = None
        if cutoff:
            base = base.where(Lead.created_at >= cutoff)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    if total == 0:
        return {
            "action": "contacts_not_found",
            "message": "No encontré contactos con esos criterios. Prueba con otros filtros.",
        }

    rows = (await db.execute(base.limit(5))).scalars().all()
    contacts = [_lead_dict(r) for r in rows]

    if total == 1:
        return {
            "action": "contact_found",
            "contact": contacts[0],
            "navigate_to": f"/contacts/{contacts[0]['id']}",
        }

    return {
        "action": "contacts_found",
        "total": total,
        "contacts": contacts,
        "filters_applied": {k: v for k, v in params.items() if v},
        "message": f"Encontré {total} contacto{'s' if total != 1 else ''}. Mostrando los primeros {len(contacts)}.",
    }


# ── 3. contact_update ─────────────────────────────────────────────────────────

async def execute_contact_update(
    params: dict[str, Any],
    user: User,
    db: AsyncSession,
    context_contact_id: str | None = None,
) -> dict:
    contact_ref = str(params.get("contact_ref", "")).strip()
    field = str(params.get("field", "")).strip()
    new_value = params.get("new_value")

    if not field:
        return {"action": "error", "message": "Se requiere el campo a modificar"}

    # Fallback to the contact visible on screen when contact_ref is empty
    if not contact_ref and context_contact_id:
        try:
            lead = await db.get(Lead, uuid.UUID(context_contact_id))
            if lead is None or lead.tenant_id != user.tenant_id:
                return {"action": "error", "message": "Contacto en pantalla no encontrado"}
        except (ValueError, TypeError):
            return {"action": "error", "message": "ID de contacto inválido"}
        leads = [lead]
    elif not contact_ref:
        return {"action": "error", "message": "Se requiere el contacto a modificar"}
    else:
        leads = await _find_leads(contact_ref, user.tenant_id, db)
    if not leads:
        return {"action": "ambiguous", "message": f"No encontré un contacto con '{contact_ref}'. ¿Puedes ser más específico?"}
    if len(leads) > 1:
        return {"action": "ambiguous", "message": f"Encontré {len(leads)} contactos con '{contact_ref}'. ¿Puedes indicar empresa o teléfono?"}

    lead = leads[0]

    if field == "status":
        try:
            lead.status = LeadStatus(new_value)
        except ValueError:
            return {"action": "error", "message": f"Estado inválido: {new_value}"}
    elif field == "assigned_to":
        result = await db.execute(
            select(User).where(User.tenant_id == user.tenant_id, User.name.ilike(f"%{new_value}%")).limit(1)
        )
        assignee = result.scalars().first()
        if not assignee:
            return {"action": "error", "message": f"No encontré al vendedor '{new_value}'"}
        lead.assigned_to = assignee.id
        new_value = assignee.name
    else:
        if hasattr(lead, field):
            setattr(lead, field, new_value)
        else:
            return {"action": "error", "message": f"Campo desconocido: {field}"}

    await db.commit()
    contact_name = f"{lead.name or ''} {lead.last_name or ''}".strip()

    return {
        "action": "contact_updated",
        "contact_id": str(lead.id),
        "contact_name": contact_name,
        "field": field,
        "new_value": str(new_value),
        "message": f"Campo actualizado correctamente en {contact_name}",
    }


# ── 4. contact_activity ───────────────────────────────────────────────────────

async def execute_contact_activity(
    params: dict[str, Any],
    user: User,
    db: AsyncSession,
    context_contact_id: str | None = None,
) -> dict:
    contact_ref = str(params.get("contact_ref", "")).strip()
    activity_type = str(params.get("activity_type", "note"))
    body_text = str(params.get("body", "")).strip()
    title = params.get("title") or None

    # Resolve lead — prefer context contact if no ref given
    if not contact_ref and context_contact_id:
        try:
            lead = await db.get(Lead, uuid.UUID(context_contact_id))
            if lead is None or lead.tenant_id != user.tenant_id:
                return {"action": "error", "message": "Contacto en pantalla no encontrado"}
        except (ValueError, TypeError):
            return {"action": "error", "message": "ID de contacto inválido"}
    else:
        leads = await _find_leads(contact_ref, user.tenant_id, db)
        if not leads:
            return {"action": "ambiguous", "message": f"No encontré a '{contact_ref}'. ¿Puedes ser más específico?"}
        if len(leads) > 1:
            return {"action": "ambiguous", "message": f"Encontré {len(leads)} contactos con '{contact_ref}'. ¿Cuál es el correcto?"}
        lead = leads[0]

    due_date: datetime | None = None
    due_date_str = params.get("due_date")
    if due_date_str:
        try:
            due_date = datetime.fromisoformat(str(due_date_str).replace("Z", "+00:00"))
        except ValueError:
            pass

    extra_data: dict[str, Any] | None = None
    duration = params.get("duration_minutes")
    if duration is not None:
        try:
            extra_data = {"duration_minutes": int(duration)}
        except (TypeError, ValueError):
            pass

    db.add(Activity(
        lead_id=lead.id,
        tenant_id=user.tenant_id,
        activity_type=activity_type,
        title=title,
        body=body_text[:1000],
        due_date=due_date,
        extra_data=extra_data,
        created_by=user.id,
    ))
    lead.last_activity_summary = (title or body_text)[:255]
    await db.commit()

    contact_name = f"{lead.name or ''} {lead.last_name or ''}".strip() or "el contacto"
    return {
        "action": "activity_created",
        "contact_id": str(lead.id),
        "contact_name": contact_name,
        "activity_type": activity_type,
        "emoji": _ACTIVITY_EMOJIS.get(activity_type, "📝"),
        "message": f"Actividad registrada para {contact_name}",
    }


# ── 5. contact_delete ─────────────────────────────────────────────────────────

async def execute_contact_delete(
    params: dict[str, Any], user: User, db: AsyncSession
) -> dict:
    # Confirmed second call
    confirmation_id = params.get("confirmation_id")
    contact_id_raw = params.get("contact_id")

    if confirmation_id and contact_id_raw:
        try:
            lead = await db.get(Lead, uuid.UUID(str(contact_id_raw)))
        except (ValueError, TypeError):
            return {"action": "error", "message": "ID de contacto inválido"}
        if lead is None or lead.tenant_id != user.tenant_id:
            return {"action": "error", "message": "Contacto no encontrado"}
        lead.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "action": "contact_deleted",
            "message": f"Contacto {lead.name or ''} archivado correctamente",
        }

    # First call: resolve and request confirmation
    contact_ref = str(params.get("contact_ref", "")).strip()
    leads = await _find_leads(contact_ref, user.tenant_id, db)

    if not leads:
        return {"action": "ambiguous", "message": f"No encontré a '{contact_ref}'"}
    if len(leads) > 1:
        return {"action": "ambiguous", "message": f"Encontré {len(leads)} contactos con '{contact_ref}'. ¿Cuál deseas archivar?"}

    lead = leads[0]
    contact_name = f"{lead.name or ''} {lead.last_name or ''}".strip()

    return {
        "action": "requires_confirmation",
        "confirmation_id": str(uuid.uuid4()),
        "contact_id": str(lead.id),
        "contact_name": contact_name,
        "message": f"¿Archivar a {contact_name}? Sus conversaciones de WhatsApp se conservarán.",
        "confirm_action": "contact_delete_confirmed",
    }
