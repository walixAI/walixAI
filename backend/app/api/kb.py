import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ingestion import ingest_all_documents
from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.knowledge import KnowledgeDocument
from app.models.user import User, UserRole

router = APIRouter(prefix="/kb", tags=["kb"])

_REINDEX_ROLES = {UserRole.OWNER, UserRole.IT}
_STATUS_ROLES = {UserRole.OWNER, UserRole.GERENTE, UserRole.IT}

# Keeps strong references so background tasks aren't GC'd mid-execution.
_background_tasks: set[asyncio.Task] = set()


class DocumentStatus(BaseModel):
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
