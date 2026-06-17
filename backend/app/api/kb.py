"""Knowledge Base endpoints for Walix.

Rutas existentes (no modificar):
  POST /api/kb/reindex            — re-indexa archivos del disco
  GET  /api/kb/status             — resumen de documentos indexados
  POST /api/kb/fragments          — alias legacy de POST /api/kb/documents

Nuevos (Sprint 12 §6):
  GET    /api/kb/documents              — lista paginada (sin embeddings)
  GET    /api/kb/documents/{id}         — documento completo (sin embeddings)
  POST   /api/kb/documents              — crea documento y genera embeddings
  PATCH  /api/kb/documents/{id}         — actualiza título/contenido
  DELETE /api/kb/documents/{id}         — elimina; pide confirmación si is_auto_generated
"""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ingestion import (
    _generate_embeddings,
    _sha256,
    _split_with_overlap,
    ingest_all_documents,
)
from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.user import User, UserRole

router = APIRouter(prefix="/kb", tags=["kb"])

_REINDEX_ROLES = {UserRole.OWNER, UserRole.IT}
_STATUS_ROLES  = {UserRole.OWNER, UserRole.GERENTE, UserRole.IT}
_DOC_ROLES     = {UserRole.OWNER, UserRole.GERENTE, UserRole.IT}

_background_tasks: set[asyncio.Task] = set()


# ── Shared helpers ────────────────────────────────────────────────────────────

def _require_roles(allowed: set[UserRole], user: User) -> None:
    if user.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para esta acción")


async def _embed_and_store(
    content: str,
    doc_id: uuid.UUID,
    tenant_id: uuid.UUID,
    title: str,
    db: AsyncSession,
) -> int:
    """Genera embeddings y crea los KnowledgeChunk rows. Retorna chunk count."""
    from openai import AsyncOpenAI
    from app.core.config import settings

    if not getattr(settings, "OPENAI_API_KEY", None):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY no configurado")

    chunks = _split_with_overlap(content)
    if not chunks:
        raise HTTPException(status_code=422, detail="El contenido no pudo dividirse en fragmentos")

    try:
        oai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        embeddings = await _generate_embeddings(oai, [c["text"] for c in chunks])
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Error generando embeddings: {exc}") from exc

    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        db.add(KnowledgeChunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            tenant_id=tenant_id,
            chunk_index=i,
            content=chunk["text"],
            embedding=emb,
            token_count=chunk.get("token_count"),
            chunk_metadata={"section": chunk.get("section", ""), "title": title},
        ))
    return len(chunks)


# ── Schemas ───────────────────────────────────────────────────────────────────

class DocumentStatus(BaseModel):
    id: uuid.UUID
    filename: str
    title: str
    chunk_count: int
    indexed_at: datetime | None


class KBStatusResponse(BaseModel):
    documents: list[DocumentStatus]
    total_documents: int
    total_chunks: int
    last_indexed: datetime | None


class ReindexResponse(BaseModel):
    message: str
    status: str


class DocumentListItem(BaseModel):
    id: uuid.UUID
    title: str
    content_preview: str | None
    chunk_count: int
    is_auto_generated: bool
    created_at: datetime


class DocumentDetail(BaseModel):
    id: uuid.UUID
    title: str
    content: str | None
    chunk_count: int
    is_auto_generated: bool
    created_at: datetime
    updated_at: datetime


class DocumentIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=10, max_length=20_000)


class DocumentPatchIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    content: str | None = Field(None, min_length=10, max_length=20_000)


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    chunk_count: int
    is_auto_generated: bool
    created_at: datetime


# ── Legacy: GET /status, POST /reindex ───────────────────────────────────────

@router.post("/reindex", response_model=ReindexResponse)
async def reindex_kb(current_user: User = Depends(get_current_user)) -> ReindexResponse:
    _require_roles(_REINDEX_ROLES, current_user)
    task = asyncio.create_task(
        ingest_all_documents(tenant_id=current_user.tenant_id, branch_id=current_user.branch_id)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return ReindexResponse(message="Re-indexación iniciada en background", status="processing")


@router.get("/status", response_model=KBStatusResponse)
async def kb_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KBStatusResponse:
    _require_roles(_STATUS_ROLES, current_user)
    rows = (await db.execute(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.tenant_id == current_user.tenant_id)
        .order_by(KnowledgeDocument.filename)
    )).scalars().all()
    documents = [
        DocumentStatus(id=d.id, filename=d.filename, title=d.title,
                       chunk_count=d.chunk_count, indexed_at=d.indexed_at)
        for d in rows
    ]
    total_chunks = sum(d.chunk_count for d in documents)
    last_indexed = max((d.indexed_at for d in documents if d.indexed_at), default=None)
    return KBStatusResponse(documents=documents, total_documents=len(documents),
                            total_chunks=total_chunks, last_indexed=last_indexed)


# ── GET /api/kb/documents ─────────────────────────────────────────────────────

@router.get("/documents", response_model=list[DocumentListItem])
async def list_documents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentListItem]:
    """Lista paginada de documentos KB — sin embeddings."""
    _require_roles(_DOC_ROLES, current_user)
    offset = (page - 1) * limit
    rows = (await db.execute(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.tenant_id == current_user.tenant_id)
        .order_by(KnowledgeDocument.created_at.desc())
        .offset(offset).limit(limit)
    )).scalars().all()
    return [
        DocumentListItem(
            id=d.id,
            title=d.title,
            content_preview=d.content[:200] if d.content else None,
            chunk_count=d.chunk_count,
            is_auto_generated=d.is_auto_generated,
            created_at=d.created_at,
        )
        for d in rows
    ]


# ── GET /api/kb/documents/{doc_id} ───────────────────────────────────────────

@router.get("/documents/{doc_id}", response_model=DocumentDetail)
async def get_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    """Retorna documento completo sin embeddings."""
    _require_roles(_DOC_ROLES, current_user)
    doc = (await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    # If content not stored (file-based doc), reconstruct from chunks
    content = doc.content
    if content is None:
        chunk_rows = (await db.execute(
            select(KnowledgeChunk.content, KnowledgeChunk.chunk_index)
            .where(KnowledgeChunk.document_id == doc_id)
            .order_by(KnowledgeChunk.chunk_index)
        )).all()
        if chunk_rows:
            content = "\n\n".join(r[0] for r in chunk_rows)

    return DocumentDetail(
        id=doc.id, title=doc.title, content=content,
        chunk_count=doc.chunk_count, is_auto_generated=doc.is_auto_generated,
        created_at=doc.created_at, updated_at=doc.updated_at,
    )


# ── POST /api/kb/documents ───────────────────────────────────────────────────

@router.post("/documents", response_model=DocumentOut, status_code=201)
async def create_document(
    body: DocumentIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    """Crea un nuevo documento KB y genera sus embeddings."""
    _require_roles(_REINDEX_ROLES, current_user)
    content_hash = _sha256(body.content)

    # Idempotent: same content already indexed
    existing = (await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == current_user.tenant_id,
            KnowledgeDocument.content_hash == content_hash,
        )
    )).scalar_one_or_none()
    if existing:
        return DocumentOut(id=existing.id, title=existing.title,
                           chunk_count=existing.chunk_count,
                           is_auto_generated=existing.is_auto_generated,
                           created_at=existing.created_at)

    now = datetime.now(timezone.utc)
    doc_id = uuid.uuid4()
    doc = KnowledgeDocument(
        id=doc_id,
        branch_id=current_user.branch_id,
        tenant_id=current_user.tenant_id,
        filename=f"doc_{doc_id.hex[:8]}.txt",
        title=body.title,
        content=body.content,
        content_hash=content_hash,
        chunk_count=0,
        indexed_at=now,
        is_auto_generated=False,
    )
    db.add(doc)
    await db.flush()

    chunk_count = await _embed_and_store(body.content, doc_id, current_user.tenant_id, body.title, db)
    doc.chunk_count = chunk_count
    await db.commit()

    return DocumentOut(id=doc_id, title=body.title, chunk_count=chunk_count,
                       is_auto_generated=False, created_at=now)


# ── PATCH /api/kb/documents/{doc_id} ─────────────────────────────────────────

@router.patch("/documents/{doc_id}", response_model=DocumentOut)
async def update_document(
    doc_id: uuid.UUID,
    body: DocumentPatchIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    """Actualiza título y/o contenido. Regenera embeddings si el contenido cambió."""
    _require_roles(_REINDEX_ROLES, current_user)
    doc = (await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if body.title is not None:
        doc.title = body.title

    if body.content is not None:
        new_hash = _sha256(body.content)
        if new_hash != doc.content_hash:
            # Delete old chunks and regenerate
            await db.execute(sa_delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id))
            await db.flush()
            chunk_count = await _embed_and_store(body.content, doc_id, current_user.tenant_id,
                                                  doc.title, db)
            doc.content = body.content
            doc.content_hash = new_hash
            doc.chunk_count = chunk_count
            doc.indexed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(doc)
    return DocumentOut(id=doc.id, title=doc.title, chunk_count=doc.chunk_count,
                       is_auto_generated=doc.is_auto_generated, created_at=doc.created_at)


# ── DELETE /api/kb/documents/{doc_id} ────────────────────────────────────────

@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: uuid.UUID,
    confirm: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Elimina un documento y sus chunks.

    Si el documento es auto-generado (from onboarding), retorna un warning
    y requiere ?confirm=true para proceder.
    """
    _require_roles(_REINDEX_ROLES, current_user)
    doc = (await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if doc.is_auto_generated and not confirm:
        return {
            "warning": "Este documento fue generado automáticamente desde tu onboarding. "
                       "Eliminarlo puede afectar la calidad de las respuestas del bot.",
            "confirm_url": f"/api/kb/documents/{doc_id}?confirm=true",
            "deleted": False,
        }

    await db.execute(sa_delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id))
    await db.delete(doc)
    await db.commit()
    return {"deleted": True, "id": str(doc_id)}


# ── Legacy: POST /fragments, DELETE /fragments/{id} ──────────────────────────
# Kept for backward compatibility with Settings.tsx Sprint 12 code.

class FragmentIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=10, max_length=10_000)


class FragmentOut(BaseModel):
    id: uuid.UUID
    title: str
    chunk_count: int
    indexed_at: str | None


@router.post("/fragments", response_model=FragmentOut, status_code=201)
async def add_kb_fragment(
    body: FragmentIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FragmentOut:
    """Alias legacy → POST /api/kb/documents."""
    _require_roles(_REINDEX_ROLES, current_user)
    content_hash = _sha256(body.content)

    existing = (await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == current_user.tenant_id,
            KnowledgeDocument.content_hash == content_hash,
        )
    )).scalar_one_or_none()
    if existing:
        return FragmentOut(id=existing.id, title=existing.title, chunk_count=existing.chunk_count,
                           indexed_at=existing.indexed_at.isoformat() if existing.indexed_at else None)

    now = datetime.now(timezone.utc)
    doc_id = uuid.uuid4()
    doc = KnowledgeDocument(
        id=doc_id, branch_id=current_user.branch_id, tenant_id=current_user.tenant_id,
        filename=f"fragment_{doc_id.hex[:8]}.txt", title=body.title, content=body.content,
        content_hash=content_hash, chunk_count=0, indexed_at=now, is_auto_generated=False,
    )
    db.add(doc)
    await db.flush()

    chunk_count = await _embed_and_store(body.content, doc_id, current_user.tenant_id, body.title, db)
    doc.chunk_count = chunk_count
    await db.commit()

    return FragmentOut(id=doc_id, title=body.title, chunk_count=chunk_count, indexed_at=now.isoformat())


@router.delete("/fragments/{document_id}", status_code=204)
async def delete_kb_fragment(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Alias legacy → DELETE /api/kb/documents/{id} (sin warning de auto-generated)."""
    _require_roles(_REINDEX_ROLES, current_user)
    doc = (await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Fragmento no encontrado")
    await db.execute(sa_delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
    await db.delete(doc)
    await db.commit()
