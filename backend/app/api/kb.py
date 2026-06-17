import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ingestion import ingest_all_documents, _split_with_overlap, _generate_embeddings, _sha256, EMBEDDING_MODEL, EMBEDDING_DIMS
from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.user import User, UserRole

router = APIRouter(prefix="/kb", tags=["kb"])

_REINDEX_ROLES = {UserRole.OWNER, UserRole.IT}
_STATUS_ROLES = {UserRole.OWNER, UserRole.GERENTE, UserRole.IT}

# Keeps strong references so background tasks aren't GC'd mid-execution.
_background_tasks: set[asyncio.Task] = set()


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


def _require_roles(allowed: set[UserRole], user: User) -> None:
    if user.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta acción",
        )


@router.post("/reindex", response_model=ReindexResponse)
async def reindex_kb(
    current_user: User = Depends(get_current_user),
) -> ReindexResponse:
    _require_roles(_REINDEX_ROLES, current_user)

    task = asyncio.create_task(
        ingest_all_documents(
            tenant_id=current_user.tenant_id,
            branch_id=current_user.branch_id,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return ReindexResponse(
        message="Re-indexación iniciada en background",
        status="processing",
    )


@router.get("/status", response_model=KBStatusResponse)
async def kb_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KBStatusResponse:
    _require_roles(_STATUS_ROLES, current_user)

    rows = (
        await db.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == current_user.tenant_id)
            .order_by(KnowledgeDocument.filename)
        )
    ).scalars().all()

    documents = [
        DocumentStatus(
            id=doc.id,
            filename=doc.filename,
            title=doc.title,
            chunk_count=doc.chunk_count,
            indexed_at=doc.indexed_at,
        )
        for doc in rows
    ]

    total_chunks = sum(d.chunk_count for d in documents)
    last_indexed = max(
        (d.indexed_at for d in documents if d.indexed_at is not None),
        default=None,
    )

    return KBStatusResponse(
        documents=documents,
        total_documents=len(documents),
        total_chunks=total_chunks,
        last_indexed=last_indexed,
    )


# ── POST /api/kb/fragments ────────────────────────────────────────────────────

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
    """Agrega un fragmento de texto directamente al KB sin subir archivo.

    Ideal para pegar la descripción del negocio, preguntas frecuentes,
    servicios, precios o cualquier texto que el bot deba conocer.
    Requiere OPENAI_API_KEY para generar embeddings.
    """
    _require_roles(_REINDEX_ROLES, current_user)

    from openai import AsyncOpenAI
    from app.core.config import settings as app_settings

    content_hash = _sha256(body.content)

    # Upsert document
    existing = (await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == current_user.tenant_id,
            KnowledgeDocument.content_hash == content_hash,
        )
    )).scalar_one_or_none()

    if existing:
        return FragmentOut(
            id=existing.id,
            title=existing.title,
            chunk_count=existing.chunk_count,
            indexed_at=existing.indexed_at.isoformat() if existing.indexed_at else None,
        )

    # Split into chunks
    chunks = _split_with_overlap(body.content)
    if not chunks:
        raise HTTPException(status_code=422, detail="El contenido no pudo dividirse en fragmentos")

    # Generate embeddings via OpenAI
    try:
        oai_client = AsyncOpenAI(api_key=app_settings.OPENAI_API_KEY)
        texts = [c["text"] for c in chunks]
        embeddings = await _generate_embeddings(oai_client, texts)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error generando embeddings: {exc}. Verifica OPENAI_API_KEY.",
        ) from exc

    now = datetime.now(timezone.utc)
    doc_id = uuid.uuid4()
    doc = KnowledgeDocument(
        id=doc_id,
        branch_id=current_user.branch_id,
        tenant_id=current_user.tenant_id,
        filename=f"fragment_{doc_id.hex[:8]}.txt",
        title=body.title,
        content_hash=content_hash,
        chunk_count=len(chunks),
        indexed_at=now,
    )
    db.add(doc)
    await db.flush()

    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        db.add(KnowledgeChunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            tenant_id=current_user.tenant_id,
            chunk_index=i,
            content=chunk["text"],
            embedding=emb,
            token_count=chunk.get("token_count"),
            chunk_metadata={"section": chunk.get("section", ""), "title": body.title},
        ))

    await db.commit()
    return FragmentOut(
        id=doc_id,
        title=body.title,
        chunk_count=len(chunks),
        indexed_at=now.isoformat(),
    )


@router.delete("/fragments/{document_id}", status_code=204)
async def delete_kb_fragment(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Elimina un documento y todos sus chunks del KB."""
    _require_roles(_REINDEX_ROLES, current_user)

    from sqlalchemy import delete as sa_delete

    doc = (await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()

    if doc is None:
        raise HTTPException(status_code=404, detail="Fragmento no encontrado")

    await db.execute(
        sa_delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
    )
    await db.delete(doc)
    await db.commit()
