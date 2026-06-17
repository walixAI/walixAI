import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Sprint 12: full text for API-created documents; null for file-based
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True when auto-created from onboarding description
    is_auto_generated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "metadata" is reserved by SQLAlchemy's DeclarativeBase — use chunk_metadata
    # as the Python attribute name while keeping the DB column as "metadata".
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
