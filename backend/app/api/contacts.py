from __future__ import annotations

import base64
import csv
import io
import json
import logging
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa
from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.bot_engine import find_lead_by_phone
from app.api.auth import get_current_user
from app.core.database import AsyncSessionLocal, get_db, set_tenant_context
from app.core.redis import redis_client
from app.services.activity_service import create_field_change_activity, create_system_activity
from app.services.whatsapp import normalize_mx_phone
from app.models.activity import Activity
from app.models.agent import AgentSuggestion
from app.models.ai_memory import AIEntityContext
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.tag import Tag, lead_tags_table
from app.models.user import User, UserRole
from app.schemas.contact import (
    ContactCreate,
    ContactListResponse,
    ContactRow,
    ContactUpdate,
    TagRow,
    UserMinimal,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/contacts", tags=["contacts"])

# ── Role sets ─────────────────────────────────────────────────────────────────
PAGE_SIZE = 25
_MANAGER_ROLES = frozenset({UserRole.OWNER, UserRole.GERENTE, UserRole.IT})
_IMPORT_ROLES = frozenset({UserRole.OWNER, UserRole.GERENTE, UserRole.IT})
_EXPORT_ROLES = frozenset({
    UserRole.OWNER, UserRole.GERENTE, UserRole.ASESOR,
    UserRole.DOCTOR, UserRole.IT,
})
# Fields tracked for field-history activities on PATCH
_MONITORED_FIELDS = frozenset({
    "name", "last_name", "company", "prospection_source",
    "status", "assigned_to",
})

# ── Sort map ──────────────────────────────────────────────────────────────────
_SORT_COLS: dict[str, Any] = {
    "name": Lead.name,
    "company": Lead.company,
    "status": Lead.status,
    "lastActivity": Lead.updated_at,
}

# ── CSV constants ─────────────────────────────────────────────────────────────
_IMPORT_MAX_BYTES = 10 * 1024 * 1024   # 10 MB
_IMPORT_MAX_ROWS = 1000
_JOB_KEY = "import_job:{}"
_JOB_TTL = 86_400                       # 24 h

_EXPORT_HEADERS = [
    "nombre", "apellido", "telefono", "email", "empresa",
    "status", "fuente", "etiquetas", "vendedor_asignado",
    "score", "fecha_creacion", "ultima_actividad",
]
_PRESET_COLORS = ["#7C3AED", "#0891B2", "#059669", "#D97706", "#DC2626", "#DB2777"]

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Inline response models ────────────────────────────────────────────────────

class _PipelineStageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    color: str | None = None
    is_won: bool
    is_lost: bool


class _ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    activity_type: str
    title: str | None = None
    body: str | None = None
    extra_data: dict | None = None
    due_date: datetime | None = None
    completed_at: datetime | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime


class _AgentSuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_type: str
    trigger_description: str
    suggestion_text: str
    status: str


class ContactDetail(ContactRow):
    pipeline_stage: _PipelineStageOut | None = None
    recent_activities: list[_ActivityOut] = []
    agent_suggestions: list[_AgentSuggestionOut] = []


class BulkBody(BaseModel):
    action: Literal["reassign", "status", "tag", "delete"]
    ids: list[uuid.UUID]
    payload: dict[str, Any] = {}


class ImportJobOut(BaseModel):
    job_id: str
    total_rows: int


# ── Query builder (shared by list + export) ───────────────────────────────────

def _build_filter_query(
    tenant_id: uuid.UUID,
    *,
    q: str | None = None,
    status_filter: list[str] | None = None,
    source: list[str] | None = None,
    tag: list[uuid.UUID] | None = None,
    assigned: list[uuid.UUID] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Select:
    base: Select = select(Lead).where(
        Lead.tenant_id == tenant_id,
        Lead.deleted_at.is_(None),
    )

    if q:
        term = f"%{q}%"
        base = base.where(
            or_(
                Lead.name.ilike(term),
                Lead.last_name.ilike(term),
                Lead.company.ilike(term),
                Lead.wa_phone.ilike(term),
                Lead.contact_phone.ilike(term),
            )
        )
    if status_filter:
        valid_statuses = {s.value for s in LeadStatus}
        known = [s for s in status_filter if s in valid_statuses]
        if not known:
            return base.where(sa.false())
        base = base.where(Lead.status.in_(known))
    if source:
        base = base.where(Lead.prospection_source.in_(source))
    if tag:
        tag_subq = (
            select(lead_tags_table.c.lead_id)
            .where(lead_tags_table.c.tag_id.in_(tag))
            .distinct()
            .scalar_subquery()
        )
        base = base.where(Lead.id.in_(tag_subq))
    if assigned:
        base = base.where(Lead.assigned_to.in_(assigned))
    if date_from:
        base = base.where(
            Lead.created_at >= datetime.combine(date_from, time.min).replace(tzinfo=timezone.utc)
        )
    if date_to:
        base = base.where(
            Lead.created_at < datetime.combine(
                date_to + timedelta(days=1), time.min
            ).replace(tzinfo=timezone.utc)
        )
    return base


# ── ORM helpers ───────────────────────────────────────────────────────────────

async def _get_active_contact(
    db: AsyncSession,
    contact_id: uuid.UUID,
    tenant_id: uuid.UUID,
    *,
    load_tags: bool = False,
) -> Lead:
    q = select(Lead).where(
        Lead.id == contact_id,
        Lead.tenant_id == tenant_id,
        Lead.deleted_at.is_(None),
    )
    if load_tags:
        q = q.options(selectinload(Lead.tags))
    lead = (await db.execute(q)).scalars().first()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
    return lead


async def _build_contact_row(
    lead: Lead,
    db: AsyncSession,
    user_cache: dict[uuid.UUID, User] | None = None,
) -> ContactRow:
    tag_rows = [TagRow.model_validate(t) for t in lead.tags]

    assigned_user: UserMinimal | None = None
    if lead.assigned_to:
        user = user_cache.get(lead.assigned_to) if user_cache else None
        if user is None:
            user = await db.get(User, lead.assigned_to)
        if user:
            assigned_user = UserMinimal.model_validate(user)

    return ContactRow(
        id=lead.id,
        wa_phone=lead.wa_phone,
        name=lead.name,
        last_name=lead.last_name,
        company=lead.company,
        prospection_source=lead.prospection_source,
        deleted_at=lead.deleted_at,
        last_activity_summary=lead.last_activity_summary,
        pipeline_stage_id=lead.pipeline_stage_id,
        current_score=lead.current_score,
        current_score_trend=lead.current_score_trend,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        status=lead.status.value if hasattr(lead.status, "value") else str(lead.status) if lead.status else None,
        tags=tag_rows,
        assigned_user=assigned_user,
    )


async def _reload_with_tags(db: AsyncSession, lead_id: uuid.UUID) -> Lead:
    lead = (
        await db.execute(
            select(Lead).where(Lead.id == lead_id).options(selectinload(Lead.tags))
        )
    ).scalars().first()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
    return lead


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _normalize_phone(raw: str) -> str:
    p = raw.strip().replace(" ", "").replace("-", "")
    if p and not p.startswith("+"):
        p = "+52" + p
    return p


def _is_valid_e164(phone: str) -> bool:
    return bool(_E164_RE.match(phone))


def _csv_cell(val: Any) -> str:
    s = str(val) if val is not None else ""
    if any(c in s for c in (',', '"', '\n', '\r')):
        s = '"' + s.replace('"', '""') + '"'
    return s


def _csv_row(fields: list[Any]) -> str:
    return ",".join(_csv_cell(f) for f in fields)


async def _get_or_create_tag(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    name: str,
    cache: dict[str, uuid.UUID],
    color_offset: int,
) -> uuid.UUID:
    if name in cache:
        return cache[name]
    existing = (
        await db.execute(
            select(Tag.id).where(Tag.name == name, Tag.tenant_id == tenant_id)
        )
    ).scalars().first()
    if existing:
        cache[name] = existing
        return existing
    color = _PRESET_COLORS[(color_offset + len(cache)) % len(_PRESET_COLORS)]
    tag = Tag(tenant_id=tenant_id, name=name, color=color)
    db.add(tag)
    await db.flush()
    cache[name] = tag.id
    return tag.id


# ── Import background job ─────────────────────────────────────────────────────

async def _process_csv_import(
    job_id: str,
    rows: list[dict[str, str]],
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID | None,
) -> None:
    total = len(rows)
    errors: list[dict] = []
    processed = 0

    try:
        # ── Pass 1: format validation (no DB) ─────────────────────────────────
        pre_valid: list[dict] = []
        for i, row in enumerate(rows):
            row_num = i + 2  # 1-based, +1 for header
            name = row.get("nombre", "").strip()
            if not name:
                errors.append({"row": row_num, "reason": "missing_name", **row})
                continue

            phone_raw = row.get("telefono", "").strip()
            phone = ""
            if phone_raw:
                e164_candidate = _normalize_phone(phone_raw)
                if not _is_valid_e164(e164_candidate):
                    errors.append({"row": row_num, "reason": "invalid_phone", **row})
                    continue
                # Se guarda en el formato canónico SIN + (mismo que usa
                # bot_engine.py para WhatsApp inbound) — antes se guardaba
                # en E.164 con + acá, un formato distinto para el mismo
                # número real que WhatsApp inbound, así que nunca hacían
                # match entre sí. Hallazgo de leads duplicados, 2026-08-25
                # — ver app.services.whatsapp.normalize_mx_phone. Esto
                # asume números mexicanos (igual que normalize_mx_phone);
                # _is_valid_e164 arriba sigue validando cualquier país.
                phone = normalize_mx_phone(e164_candidate) or e164_candidate

            email = row.get("email", "").strip()
            if email and not _EMAIL_RE.match(email):
                errors.append({"row": row_num, "reason": "invalid_email", **row})
                continue

            pre_valid.append({
                "_row_num": row_num,
                "_raw": row,
                "name": name,
                "last_name": row.get("apellido", "").strip() or None,
                "phone": phone,
                "company": row.get("empresa", "").strip() or None,
                "status_raw": row.get("status", "").strip(),
                "fuente": row.get("fuente", "").strip() or "manual",
                "etiquetas": [
                    t.strip()
                    for t in row.get("etiquetas", "").split("|")
                    if t.strip()
                ],
            })

        # ── Pass 2: batch duplicate phone check ───────────────────────────────
        real_phones = [r["phone"] for r in pre_valid if r["phone"]]
        existing_phones: set[str] = set()

        async with AsyncSessionLocal() as db:
            await set_tenant_context(db, tenant_id)
            if real_phones:
                existing_phones = set(
                    (
                        await db.execute(
                            select(Lead.wa_phone).where(
                                Lead.wa_phone.in_(real_phones),
                                Lead.tenant_id == tenant_id,
                                Lead.deleted_at.is_(None),
                            )
                        )
                    ).scalars().all()
                )

            # Round-robin color offset: count of existing tags for this tenant
            color_offset = (
                await db.execute(
                    select(func.count(Tag.id)).where(Tag.tenant_id == tenant_id)
                )
            ).scalar_one()
            tag_cache: dict[str, uuid.UUID] = {}

            # ── Pass 3: insert ────────────────────────────────────────────────
            for r in pre_valid:
                if r["phone"] and r["phone"] in existing_phones:
                    errors.append({
                        "row": r["_row_num"],
                        "reason": "duplicate_phone",
                        **r["_raw"],
                    })
                    continue

                # Use placeholder when no phone provided (wa_phone is NOT NULL)
                final_phone = r["phone"] or f"NOPHONE_{uuid.uuid4().hex[:16].upper()}"

                # Map status string to enum; default NUEVO on mismatch
                lead_status = LeadStatus.NUEVO
                if r["status_raw"]:
                    try:
                        lead_status = LeadStatus(r["status_raw"])
                    except ValueError:
                        pass

                lead = Lead(
                    branch_id=branch_id,
                    tenant_id=tenant_id,
                    wa_phone=final_phone,
                    name=r["name"],
                    last_name=r["last_name"],
                    company=r["company"],
                    prospection_source=r["fuente"],
                    status=lead_status,
                    source=LeadSource.MANUAL,
                    sentiment=LeadSentiment.NEUTRAL,
                )
                db.add(lead)
                await db.flush()

                for tag_name in r["etiquetas"]:
                    tag_id = await _get_or_create_tag(
                        db, tenant_id, tag_name, tag_cache, color_offset
                    )
                    await db.execute(
                        pg_insert(lead_tags_table)
                        .values(lead_id=lead.id, tag_id=tag_id)
                        .on_conflict_do_nothing()
                    )

                processed += 1

                if processed % 10 == 0:
                    await db.flush()
                    await redis_client.set(
                        _JOB_KEY.format(job_id),
                        json.dumps({
                            "status": "processing",
                            "processed": processed,
                            "total": total,
                            "errors": errors[-100:],
                            "tenant_id": str(tenant_id),
                        }),
                        ex=_JOB_TTL,
                    )

            await db.commit()

        # ── Build error CSV (base64) if needed ────────────────────────────────
        error_csv_b64: str | None = None
        if errors and rows:
            buf = io.StringIO()
            fieldnames = list(rows[0].keys()) + ["error"]
            writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for e in errors:
                row_data = {k: e.get(k, "") for k in fieldnames}
                row_data["error"] = e.get("reason", "unknown")
                writer.writerow(row_data)
            error_csv_b64 = base64.b64encode(buf.getvalue().encode("utf-8")).decode("ascii")

        payload: dict[str, Any] = {
            "status": "completed",
            "processed": processed,
            "total": total,
            "errors": errors,
            "tenant_id": str(tenant_id),
        }
        if error_csv_b64:
            payload["error_csv_base64"] = error_csv_b64

        await redis_client.set(_JOB_KEY.format(job_id), json.dumps(payload), ex=_JOB_TTL)

    except Exception:
        logger.exception("import job %s failed", job_id)
        await redis_client.set(
            _JOB_KEY.format(job_id),
            json.dumps({
                "status": "failed",
                "processed": processed,
                "total": total,
                "errors": errors,
                "tenant_id": str(tenant_id),
            }),
            ex=_JOB_TTL,
        )


# ── 1. GET / — paginated list ─────────────────────────────────────────────────

@router.get("", response_model=ContactListResponse)
async def list_contacts(
    q: str | None = Query(default=None),
    status_filter: list[str] = Query(default=[], alias="status"),
    source: list[str] = Query(default=[]),
    tag: list[uuid.UUID] = Query(default=[]),
    assigned: list[uuid.UUID] = Query(default=[]),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort: Literal["name", "company", "status", "lastActivity"] = Query(default="name"),
    order: Literal["asc", "desc"] = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactListResponse:
    base = _build_filter_query(
        current_user.tenant_id,
        q=q,
        status_filter=status_filter,
        source=source,
        tag=tag,
        assigned=assigned,
        date_from=date_from,
        date_to=date_to,
    )

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    sort_col = _SORT_COLS.get(sort, Lead.name)
    order_expr = sort_col.desc() if order == "desc" else sort_col.asc()

    leads = (
        await db.execute(
            base
            .options(selectinload(Lead.tags))
            .order_by(order_expr, Lead.created_at.desc())
            .limit(PAGE_SIZE)
            .offset((page - 1) * PAGE_SIZE)
        )
    ).scalars().all()

    user_ids = {lead.assigned_to for lead in leads if lead.assigned_to}
    user_cache: dict[uuid.UUID, User] = {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
            user_cache[u.id] = u

    items = [await _build_contact_row(lead, db, user_cache) for lead in leads]
    return ContactListResponse(items=items, total=total, page=page, page_size=PAGE_SIZE)


# ── 2. POST / — create contact ────────────────────────────────────────────────

@router.post("", response_model=ContactRow, status_code=status.HTTP_201_CREATED)
async def create_contact(
    body: ContactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactRow:
    if current_user.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tienes una sucursal asignada",
        )

    # Normalizado — antes se guardaba tal cual lo haya tipeado el usuario en
    # el form, sin match posible contra un lead que ya escribió por
    # WhatsApp con el mismo número real en formato canónico. Hallazgo de
    # leads duplicados, 2026-08-25 — ver app.services.whatsapp.normalize_mx_phone.
    wa_phone = normalize_mx_phone(body.wa_phone) if body.wa_phone else None

    if not body.name and not wa_phone:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Se requiere al menos el nombre o el teléfono del contacto",
        )

    if wa_phone:
        existing = await find_lead_by_phone(db, wa_phone, current_user.branch_id, current_user.tenant_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe un contacto con este teléfono: {existing.name or existing.wa_phone} (id={existing.id})",
            )

    lead = Lead(
        branch_id=current_user.branch_id,
        tenant_id=current_user.tenant_id,
        wa_phone=wa_phone,
        name=body.name,
        last_name=body.last_name,
        company=body.company,
        prospection_source=body.prospection_source,
        pipeline_stage_id=body.pipeline_stage_id,
        assigned_to=current_user.id,
        status=LeadStatus.NUEVO,
        source=LeadSource.MANUAL,
        sentiment=LeadSentiment.NEUTRAL,
    )
    db.add(lead)
    await db.flush()

    if body.tag_ids:
        valid_tag_ids = (
            await db.execute(
                select(Tag.id).where(
                    Tag.id.in_(body.tag_ids),
                    Tag.tenant_id == current_user.tenant_id,
                )
            )
        ).scalars().all()
        if valid_tag_ids:
            await db.execute(
                pg_insert(lead_tags_table)
                .values([{"lead_id": lead.id, "tag_id": tid} for tid in valid_tag_ids])
                .on_conflict_do_nothing()
            )

    await db.commit()
    lead = await _reload_with_tags(db, lead.id)
    return await _build_contact_row(lead, db)


# ── 5. DELETE /{id} ───────────────────────────────────────────────────────────

@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    lead = await _get_active_contact(db, contact_id, current_user.tenant_id)

    if current_user.role not in _MANAGER_ROLES and lead.assigned_to != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para eliminar este contacto",
        )

    lead.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ── 6. POST /bulk ─────────────────────────────────────────────────────────────

@router.post("/bulk", response_model=dict)
async def bulk_action(
    body: BulkBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not body.ids:
        return {"updated": 0}

    if body.action == "delete" and current_user.role not in _MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol gerente o superior para eliminar en lote",
        )

    owned = set(
        (
            await db.execute(
                select(Lead.id).where(
                    Lead.id.in_(body.ids),
                    Lead.tenant_id == current_user.tenant_id,
                    Lead.deleted_at.is_(None),
                )
            )
        ).scalars().all()
    )
    if owned != set(body.ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Uno o más contactos no pertenecen a tu cuenta",
        )

    valid_ids = list(owned)
    updated: int = 0

    if body.action == "reassign":
        raw_uid = body.payload.get("user_id")
        if not raw_uid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payload.user_id es requerido")
        try:
            assignee_id = uuid.UUID(str(raw_uid))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payload.user_id debe ser un UUID válido")
        result = await db.execute(update(Lead).where(Lead.id.in_(valid_ids)).values(assigned_to=assignee_id))
        updated = result.rowcount

    elif body.action == "status":
        new_status = body.payload.get("status")
        if not new_status:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payload.status es requerido")
        try:
            validated_status = LeadStatus(new_status)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Estado inválido: {new_status}")
        result = await db.execute(update(Lead).where(Lead.id.in_(valid_ids)).values(status=validated_status))
        updated = result.rowcount

    elif body.action == "tag":
        raw_tid = body.payload.get("tag_id")
        if not raw_tid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payload.tag_id es requerido")
        try:
            tag_id = uuid.UUID(str(raw_tid))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payload.tag_id debe ser un UUID válido")
        tag = await db.get(Tag, tag_id)
        if tag is None or tag.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag no encontrado")
        await db.execute(
            pg_insert(lead_tags_table)
            .values([{"lead_id": lid, "tag_id": tag_id} for lid in valid_ids])
            .on_conflict_do_nothing()
        )
        updated = len(valid_ids)

    elif body.action == "delete":
        result = await db.execute(
            update(Lead).where(Lead.id.in_(valid_ids)).values(deleted_at=datetime.now(timezone.utc))
        )
        updated = result.rowcount

    await db.commit()
    return {"updated": updated}


# ── 7. POST /import ───────────────────────────────────────────────────────────

@router.post("/import", response_model=ImportJobOut, status_code=status.HTTP_202_ACCEPTED)
async def import_contacts(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportJobOut:
    if current_user.role not in _IMPORT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol gerente o superior para importar contactos",
        )

    content = await file.read()
    if len(content) > _IMPORT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo supera el límite de {_IMPORT_MAX_BYTES // 1024 // 1024} MB",
        )

    # Decode: utf-8-sig strips BOM that Excel emits
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo leer el archivo — usa UTF-8 o Latin-1",
            )

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo CSV está vacío")

    # Normalize header names to lowercase, stripped
    normalized_headers = [h.strip().lower() for h in reader.fieldnames]
    if "nombre" not in normalized_headers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El CSV debe tener al menos la columna 'nombre'",
        )

    # Re-read with normalized fieldnames
    reader.fieldnames = normalized_headers
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append({k.strip().lower(): (v or "").strip() for k, v in row.items()})
        if len(rows) >= _IMPORT_MAX_ROWS:
            break  # silently truncate; total_rows will reflect actual count

    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El CSV no contiene filas de datos")

    job_id = uuid.uuid4().hex

    await redis_client.set(
        _JOB_KEY.format(job_id),
        json.dumps({
            "status": "processing",
            "processed": 0,
            "total": len(rows),
            "errors": [],
            "tenant_id": str(current_user.tenant_id),
        }),
        ex=_JOB_TTL,
    )

    background_tasks.add_task(
        _process_csv_import,
        job_id,
        rows,
        current_user.tenant_id,
        current_user.branch_id,
    )

    return ImportJobOut(job_id=job_id, total_rows=len(rows))


# ── 8. GET /import/{job_id} ───────────────────────────────────────────────────

@router.get("/import/{job_id}")
async def get_import_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    raw = await redis_client.get(_JOB_KEY.format(job_id))
    if raw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job no encontrado o expirado")

    data: dict = json.loads(raw)

    # Tenants can only see their own jobs
    if data.get("tenant_id") != str(current_user.tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job no encontrado o expirado")

    return data


# ── 9. GET /export ────────────────────────────────────────────────────────────

@router.get("/export")
async def export_contacts(
    q: str | None = Query(default=None),
    status_filter: list[str] = Query(default=[], alias="status"),
    source: list[str] = Query(default=[]),
    tag: list[uuid.UUID] = Query(default=[]),
    assigned: list[uuid.UUID] = Query(default=[]),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    if current_user.role not in _EXPORT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para exportar contactos",
        )

    base = _build_filter_query(
        current_user.tenant_id,
        q=q,
        status_filter=status_filter,
        source=source,
        tag=tag,
        assigned=assigned,
        date_from=date_from,
        date_to=date_to,
    ).order_by(Lead.created_at.desc())

    filename = f"walix-contactos-{date.today().isoformat()}.csv"

    async def generate():
        # UTF-8 BOM — required for Excel en español
        yield b"\xef\xbb\xbf"
        yield (_csv_row(_EXPORT_HEADERS) + "\r\n").encode("utf-8")

        offset = 0
        while True:
            chunk = (
                await db.execute(
                    base
                    .options(selectinload(Lead.tags))
                    .limit(100)
                    .offset(offset)
                )
            ).scalars().all()

            if not chunk:
                break

            # Batch-load assigned users
            user_ids = {lead.assigned_to for lead in chunk if lead.assigned_to}
            user_map: dict[uuid.UUID, User] = {}
            if user_ids:
                for u in (
                    await db.execute(select(User).where(User.id.in_(user_ids)))
                ).scalars().all():
                    user_map[u.id] = u

            for lead in chunk:
                assignee_name = ""
                if lead.assigned_to and lead.assigned_to in user_map:
                    assignee_name = user_map[lead.assigned_to].name or ""

                tags_str = "|".join(t.name for t in lead.tags)
                qdata = lead.qualification_data or {}

                fields = [
                    lead.name or "",
                    lead.last_name or "",
                    lead.wa_phone or "",
                    qdata.get("email", ""),
                    lead.company or "",
                    lead.status.value if lead.status else "",
                    lead.prospection_source or "",
                    tags_str,
                    assignee_name,
                    str(lead.current_score) if lead.current_score is not None else "",
                    lead.created_at.strftime("%Y-%m-%d %H:%M:%S") if lead.created_at else "",
                    lead.updated_at.strftime("%Y-%m-%d %H:%M:%S") if lead.updated_at else "",
                ]
                yield (_csv_row(fields) + "\r\n").encode("utf-8")

            if len(chunk) < 100:
                break
            offset += 100

    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── 10. GET /{id} — full contact card ────────────────────────────────────────

@router.get("/{contact_id}", response_model=ContactDetail)
async def get_contact(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactDetail:
    lead = await _get_active_contact(db, contact_id, current_user.tenant_id, load_tags=True)

    row = await _build_contact_row(lead, db)
    detail = ContactDetail(**row.model_dump())

    if lead.pipeline_stage_id:
        stage = await db.get(PipelineStage, lead.pipeline_stage_id)
        if stage:
            detail.pipeline_stage = _PipelineStageOut.model_validate(stage)

    acts = (
        await db.execute(
            select(Activity)
            .where(Activity.lead_id == contact_id)
            .order_by(Activity.created_at.desc())
            .limit(5)
        )
    ).scalars().all()
    detail.recent_activities = [_ActivityOut.model_validate(a) for a in acts]

    suggestions = (
        await db.execute(
            select(AgentSuggestion).where(
                AgentSuggestion.tenant_id == current_user.tenant_id,
                AgentSuggestion.status == "suggested",
                AgentSuggestion.action_payload.contains({"lead_id": str(contact_id)}),
            )
        )
    ).scalars().all()
    detail.agent_suggestions = [_AgentSuggestionOut.model_validate(s) for s in suggestions]

    return detail


# ── 11. PATCH /{id} ───────────────────────────────────────────────────────────

@router.patch("/{contact_id}", response_model=ContactRow)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactRow:
    lead = await _get_active_contact(db, contact_id, current_user.tenant_id)

    updates = body.model_dump(exclude_unset=True, exclude={"tag_ids"})

    # ── Capture before-state for monitored fields ─────────────────────────────
    before: dict[str, Any] = {
        field: getattr(lead, field, None)
        for field in updates
        if field in _MONITORED_FIELDS
    }

    # Capture current tag set before wipe (only if tag_ids is being updated)
    tags_before: frozenset[uuid.UUID] | None = None
    if body.tag_ids is not None:
        tag_id_rows = (
            await db.execute(
                select(lead_tags_table.c.tag_id).where(
                    lead_tags_table.c.lead_id == contact_id
                )
            )
        ).scalars().all()
        tags_before = frozenset(tag_id_rows)

    # ── Apply field updates ───────────────────────────────────────────────────
    for field, value in updates.items():
        setattr(lead, field, value)

    if body.tag_ids is not None:
        await db.execute(
            delete(lead_tags_table).where(lead_tags_table.c.lead_id == contact_id)
        )
        if body.tag_ids:
            valid_tag_ids = (
                await db.execute(
                    select(Tag.id).where(
                        Tag.id.in_(body.tag_ids),
                        Tag.tenant_id == current_user.tenant_id,
                    )
                )
            ).scalars().all()
            if valid_tag_ids:
                await db.execute(
                    pg_insert(lead_tags_table)
                    .values([{"lead_id": contact_id, "tag_id": tid} for tid in valid_tag_ids])
                    .on_conflict_do_nothing()
                )

    await db.commit()
    lead = await _reload_with_tags(db, contact_id)

    # ── Build changes dict ────────────────────────────────────────────────────
    changes: dict[str, tuple[Any, Any]] = {
        field: (old_val, updates[field])
        for field, old_val in before.items()
        if old_val != updates[field]
    }

    # Resolve assigned_to UUIDs → user names for human-readable display
    if "assigned_to" in changes:
        old_uid, new_uid = changes["assigned_to"]
        old_name = "(sin asignar)"
        new_name = "(sin asignar)"
        if old_uid:
            u = await db.get(User, old_uid)
            old_name = u.name if u else str(old_uid)
        if new_uid:
            u = await db.get(User, new_uid)
            new_name = u.name if u else str(new_uid)
        changes["assigned_to"] = (old_name, new_name)

    tags_changed = tags_before is not None and frozenset(body.tag_ids or []) != tags_before

    # Build response before field-history commit so `lead` is in a clean state
    response = await _build_contact_row(lead, db)

    # ── Fire-and-forget field history (non-critical) ──────────────────────────
    if changes or tags_changed:
        try:
            if changes:
                await create_field_change_activity(
                    lead_id=lead.id,
                    tenant_id=current_user.tenant_id,
                    changed_by_id=current_user.id,
                    changed_by_name=current_user.name,
                    changes=changes,
                    db=db,
                )
            if tags_changed:
                await create_system_activity(
                    lead_id=lead.id,
                    tenant_id=current_user.tenant_id,
                    description="Etiquetas actualizadas",
                    metadata={
                        "changed_by_id": str(current_user.id),
                        "changed_by_name": current_user.name,
                    },
                    db=db,
                )
            await db.commit()
        except Exception:
            logger.exception("field history failed for contact %s", contact_id)
            await db.rollback()

    return response


# ── GET /{lead_id}/ai-context ─────────────────────────────────────────────────

class AIContextOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    context_summary: str
    key_facts: list[Any]
    last_interaction: datetime | None


@router.get("/{lead_id}/ai-context", response_model=AIContextOut)
async def get_contact_ai_context(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIContextOut:
    await _get_active_contact(db, lead_id, current_user.tenant_id)

    ctx = (await db.execute(
        select(AIEntityContext).where(
            AIEntityContext.tenant_id == current_user.tenant_id,
            AIEntityContext.entity_type == "contact",
            AIEntityContext.entity_id == lead_id,
        )
    )).scalar_one_or_none()

    if ctx is None:
        return AIContextOut(context_summary="", key_facts=[], last_interaction=None)

    return AIContextOut(
        context_summary=ctx.context_summary,
        key_facts=ctx.key_facts,
        last_interaction=ctx.last_interaction,
    )
