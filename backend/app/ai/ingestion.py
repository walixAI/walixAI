"""KB ingestion logic — shared between the CLI script and the /api/kb/reindex endpoint.

Public API:
    async def ingest_all_documents(tenant_id, branch_id, kb_dir) -> dict
"""
import asyncio
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import tiktoken
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

logger = logging.getLogger(__name__)

# Default: backend/scripts/walix_kb/  (two levels up from app/ai/)
_DEFAULT_KB_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "walix_kb"

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 1536
BATCH_SIZE = 20
BATCH_DELAY = 0.5


# ── Chunking ──────────────────────────────────────────────────────────────────

def _split_with_overlap(text: str, max_tokens: int = 512, overlap_ratio: float = 0.1) -> list[dict]:
    enc = tiktoken.get_encoding("cl100k_base")
    overlap_size = max(1, int(max_tokens * overlap_ratio))

    current_section = ""
    blocks: list[tuple[str, str]] = []
    for raw_block in re.split(r"\n{2,}", text):
        block = raw_block.strip()
        if not block:
            continue
        for line in block.splitlines():
            if line.startswith("## "):
                current_section = line.lstrip("#").strip()
                break
        blocks.append((block, current_section))

    raw_chunks: list[dict] = []
    for block_text, section in blocks:
        tokens = enc.encode(block_text)
        if len(tokens) <= max_tokens:
            raw_chunks.append({"text": block_text, "token_count": len(tokens), "section": section})
        else:
            sentences = re.split(r"(?<=[.!?…])\s+", block_text)
            buf: list[str] = []
            buf_tokens = 0
            for sent in sentences:
                s_tok = len(enc.encode(sent))
                if buf_tokens + s_tok > max_tokens and buf:
                    chunk_text = " ".join(buf)
                    raw_chunks.append({"text": chunk_text, "token_count": len(enc.encode(chunk_text)), "section": section})
                    buf, buf_tokens = [sent], s_tok
                else:
                    buf.append(sent)
                    buf_tokens += s_tok
            if buf:
                chunk_text = " ".join(buf)
                raw_chunks.append({"text": chunk_text, "token_count": len(enc.encode(chunk_text)), "section": section})

    final_chunks: list[dict] = []
    for i, chunk in enumerate(raw_chunks):
        if i == 0:
            final_chunks.append(chunk)
            continue
        prev_tokens = enc.encode(raw_chunks[i - 1]["text"])
        overlap_text = enc.decode(prev_tokens[-overlap_size:]).strip()
        new_text = overlap_text + "\n\n" + chunk["text"]
        final_chunks.append({"text": new_text, "token_count": len(enc.encode(new_text)), "section": chunk["section"]})

    return final_chunks


# ── Embeddings ────────────────────────────────────────────────────────────────

async def _generate_embeddings(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL, input=batch, dimensions=EMBEDDING_DIMS
        )
        embeddings.extend(item.embedding for item in response.data)
        if i + BATCH_SIZE < len(texts):
            await asyncio.sleep(BATCH_DELAY)
    return embeddings


# ── Per-file ingestion ────────────────────────────────────────────────────────

def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def _ingest_file(
    client: AsyncOpenAI,
    file_path: Path,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID | None,
) -> dict:
    """Index a single .md file. Returns {filename, chunks, tokens, skipped}."""
    content = file_path.read_text(encoding="utf-8")
    content_hash = _sha256(content)
    filename = file_path.name

    async with AsyncSessionLocal() as db:
        existing_doc = (
            await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeDocument.filename == filename,
                )
            )
        ).scalar_one_or_none()

        if existing_doc and existing_doc.content_hash == content_hash:
            return {"filename": filename, "chunks": 0, "tokens": 0, "skipped": True}

        title = filename.removesuffix(".md").replace("_", " ").title()
        for line in content.splitlines():
            if line.startswith("# "):
                title = line.lstrip("#").strip()
                break

        chunks = _split_with_overlap(content)
        chunk_texts = [c["text"] for c in chunks]
        total_tokens = sum(c["token_count"] for c in chunks)

        embeddings = await _generate_embeddings(client, chunk_texts)

        now = datetime.now(timezone.utc)
        if existing_doc:
            await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == existing_doc.id))
            existing_doc.content_hash = content_hash
            existing_doc.title = title
            existing_doc.chunk_count = len(chunks)
            existing_doc.indexed_at = now
            doc = existing_doc
        else:
            doc = KnowledgeDocument(
                tenant_id=tenant_id,
                branch_id=branch_id,
                filename=filename,
                title=title,
                content_hash=content_hash,
                chunk_count=len(chunks),
                indexed_at=now,
            )
            db.add(doc)

        await db.flush()

        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(
                KnowledgeChunk(
                    document_id=doc.id,
                    tenant_id=tenant_id,
                    chunk_index=idx,
                    content=chunk["text"],
                    embedding=embedding,
                    token_count=chunk["token_count"],
                    chunk_metadata={"section": chunk["section"]},
                )
            )

        await db.commit()

    return {"filename": filename, "chunks": len(chunks), "tokens": total_tokens, "skipped": False}


# ── Public entry point ────────────────────────────────────────────────────────

async def ingest_all_documents(
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID | None = None,
    kb_dir: Path | None = None,
) -> dict:
    """Index all .md files in kb_dir for the given tenant.

    Safe to call from an asyncio background task — creates its own DB sessions.
    Returns summary: {indexed, skipped, total_chunks, total_tokens, errors}.
    """
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")

    kb_path = kb_dir or _DEFAULT_KB_DIR
    md_files = sorted(kb_path.glob("*.md"))
    if not md_files:
        logger.warning("ingest_all_documents: no .md files found in %s", kb_path)
        return {"indexed": 0, "skipped": 0, "total_chunks": 0, "total_tokens": 0, "errors": []}

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    indexed = skipped = total_chunks = total_tokens = 0
    errors: list[str] = []

    for file_path in md_files:
        try:
            result = await _ingest_file(client, file_path, tenant_id, branch_id)
            if result["skipped"]:
                skipped += 1
            else:
                indexed += 1
                total_chunks += result["chunks"]
                total_tokens += result["tokens"]
            logger.info(
                "ingest: %s — %s",
                result["filename"],
                "sin cambios" if result["skipped"] else f"{result['chunks']} chunks",
            )
        except Exception:
            logger.exception("ingest: error processing %s", file_path.name)
            errors.append(file_path.name)

    logger.info(
        "ingest_all_documents: indexed=%d skipped=%d chunks=%d tokens=%d errors=%d",
        indexed, skipped, total_chunks, total_tokens, len(errors),
    )
    return {
        "indexed": indexed,
        "skipped": skipped,
        "total_chunks": total_chunks,
        "total_tokens": total_tokens,
        "errors": errors,
    }
