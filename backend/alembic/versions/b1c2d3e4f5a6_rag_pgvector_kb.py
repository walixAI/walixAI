"""Sprint 2: pgvector extension, knowledge base tables, leads RAG columns

Revision ID: b1c2d3e4f5a6
Revises: e472e38a73fa
Create Date: 2026-05-27

Changes:
- Enable pgvector extension
- Create knowledge_documents table
- Create knowledge_chunks table with vector(1536) embedding
- HNSW index for cosine similarity search
- GIN full-text search index (spanish)
- Index on knowledge_chunks.tenant_id
- Add last_rag_context, qualification_score, qualification_notes to leads
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "e472e38a73fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. pgvector extension
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # 2. knowledge_documents
    # ------------------------------------------------------------------
    op.create_table(
        "knowledge_documents",
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_documents_branch_id"),
        "knowledge_documents",
        ["branch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_documents_tenant_id"),
        "knowledge_documents",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_documents_content_hash"),
        "knowledge_documents",
        ["content_hash"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 3. knowledge_chunks — created with raw SQL because the vector(1536)
    #    column type requires the pgvector extension enabled above.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE knowledge_chunks (
            id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id   UUID         NOT NULL
                              REFERENCES knowledge_documents(id) ON DELETE CASCADE,
            tenant_id     UUID         NOT NULL
                              REFERENCES tenants(id) ON DELETE CASCADE,
            chunk_index   INTEGER      NOT NULL,
            content       TEXT         NOT NULL,
            embedding     vector(1536) NOT NULL,
            token_count   INTEGER,
            metadata      JSONB        NOT NULL DEFAULT '{}',
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index(
        "ix_knowledge_chunks_document_id",
        "knowledge_chunks",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_chunks_tenant_id",
        "knowledge_chunks",
        ["tenant_id"],
        unique=False,
    )

    # HNSW index for fast approximate cosine similarity search
    op.execute(
        """
        CREATE INDEX idx_chunks_embedding
            ON knowledge_chunks
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """
    )

    # GIN full-text search index in Spanish
    op.execute(
        """
        CREATE INDEX idx_chunks_fts
            ON knowledge_chunks
            USING gin(to_tsvector('spanish', content))
        """
    )

    # ------------------------------------------------------------------
    # 4. Add RAG / qualification columns to leads
    # ------------------------------------------------------------------
    op.add_column(
        "leads",
        sa.Column(
            "last_rag_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "leads",
        sa.Column("qualification_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("qualification_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    # Leads columns
    op.drop_column("leads", "qualification_notes")
    op.drop_column("leads", "qualification_score")
    op.drop_column("leads", "last_rag_context")

    # knowledge_chunks indexes and table
    op.execute("DROP INDEX IF EXISTS idx_chunks_fts")
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
    op.drop_index("ix_knowledge_chunks_tenant_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")

    # knowledge_documents indexes and table
    op.drop_index(
        op.f("ix_knowledge_documents_content_hash"), table_name="knowledge_documents"
    )
    op.drop_index(
        op.f("ix_knowledge_documents_tenant_id"), table_name="knowledge_documents"
    )
    op.drop_index(
        op.f("ix_knowledge_documents_branch_id"), table_name="knowledge_documents"
    )
    op.drop_table("knowledge_documents")

    # Do NOT drop the vector extension — other tables may depend on it.
