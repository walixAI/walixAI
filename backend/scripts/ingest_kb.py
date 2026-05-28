"""Indexa documentos Markdown de walix_kb/ en pgvector.

Uso (desde backend/):
    .venv/bin/python scripts/ingest_kb.py

Flags opcionales:
    --tenant-email  EMAIL  (default: admin@clinica.com)
    --branch-name   NAME   branch específico; si se omite la KB es tenant-wide
    --kb-dir        PATH   directorio de docs (default: walix_kb/ junto a este script)
    --dry-run              muestra qué se indexaría sin escribir en la BD
"""
import argparse
import asyncio
import hashlib
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tiktoken
from openai import OpenAI
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.tenant import Branch, Tenant

# ── Constantes ────────────────────────────────────────────────────────────────

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 1536
EMBEDDING_PRICE_PER_1M = 0.13   # USD, text-embedding-3-large
BATCH_SIZE = 20
BATCH_DELAY = 0.5               # segundos entre batches


# ── Chunking ──────────────────────────────────────────────────────────────────

def split_with_overlap(
    text: str,
    max_tokens: int = 512,
    overlap_ratio: float = 0.1,
) -> list[dict]:
    """Divide text en chunks con overlap.

    Retorna lista de dicts: {text, token_count, section}.
    """
    enc = tiktoken.get_encoding("cl100k_base")
    overlap_size = max(1, int(max_tokens * overlap_ratio))

    # 1. Extraer bloques (párrafos) con su sección ## más cercana
    current_section = ""
    blocks: list[tuple[str, str]] = []

    for raw_block in re.split(r"\n{2,}", text):
        block = raw_block.strip()
        if not block:
            continue
        # Actualizar sección si el bloque arranca con un heading ##
        for line in block.splitlines():
            if line.startswith("## "):
                current_section = line.lstrip("#").strip()
                break
        blocks.append((block, current_section))

    # 2. Construir chunks respetando max_tokens
    raw_chunks: list[dict] = []

    for block_text, section in blocks:
        tokens = enc.encode(block_text)
        if len(tokens) <= max_tokens:
            raw_chunks.append(
                {"text": block_text, "token_count": len(tokens), "section": section}
            )
        else:
            # El bloque es demasiado grande → dividir por oraciones
            sentences = re.split(r"(?<=[.!?…])\s+", block_text)
            buf: list[str] = []
            buf_tokens = 0
            for sent in sentences:
                s_tok = len(enc.encode(sent))
                if buf_tokens + s_tok > max_tokens and buf:
                    chunk_text = " ".join(buf)
                    raw_chunks.append(
                        {
                            "text": chunk_text,
                            "token_count": len(enc.encode(chunk_text)),
                            "section": section,
                        }
                    )
                    buf = [sent]
                    buf_tokens = s_tok
                else:
                    buf.append(sent)
                    buf_tokens += s_tok
            if buf:
                chunk_text = " ".join(buf)
                raw_chunks.append(
                    {
                        "text": chunk_text,
                        "token_count": len(enc.encode(chunk_text)),
                        "section": section,
                    }
                )

    # 3. Agregar overlap: los últimos overlap_size tokens del chunk anterior
    #    se prependen al chunk actual.
    final_chunks: list[dict] = []
    for i, chunk in enumerate(raw_chunks):
        if i == 0:
            final_chunks.append(chunk)
            continue

        prev_tokens = enc.encode(raw_chunks[i - 1]["text"])
        overlap_text = enc.decode(prev_tokens[-overlap_size:]).strip()
        new_text = overlap_text + "\n\n" + chunk["text"]
        final_chunks.append(
            {
                "text": new_text,
                "token_count": len(enc.encode(new_text)),
                "section": chunk["section"],
            }
        )

    return final_chunks


# ── Embeddings ────────────────────────────────────────────────────────────────

def generate_embeddings(
    client: OpenAI,
    texts: list[str],
) -> list[list[float]]:
    """Genera embeddings en batches con delay entre cada uno."""
    embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
            dimensions=EMBEDDING_DIMS,
        )
        embeddings.extend(item.embedding for item in response.data)

        if i + BATCH_SIZE < len(texts):
            time.sleep(BATCH_DELAY)

    return embeddings


# ── DB helpers ────────────────────────────────────────────────────────────────

def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def _find_tenant_and_branch(
    tenant_email: str,
    branch_name: str | None,
) -> tuple:
    async with AsyncSessionLocal() as db:
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.email == tenant_email)
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            print(f"ERROR: tenant '{tenant_email}' no encontrado en la BD.")
            sys.exit(1)

        branch = None
        if branch_name:
            branch_result = await db.execute(
                select(Branch).where(
                    Branch.tenant_id == tenant.id,
                    Branch.name == branch_name,
                )
            )
            branch = branch_result.scalar_one_or_none()
            if branch is None:
                print(f"ERROR: branch '{branch_name}' no encontrado.")
                sys.exit(1)

        return tenant.id, (branch.id if branch else None)


# ── Ingesta por archivo ───────────────────────────────────────────────────────

async def ingest_file(
    openai_client: OpenAI,
    file_path: Path,
    tenant_id,
    branch_id,
    dry_run: bool,
) -> dict:
    """Indexa un archivo .md. Retorna stats del archivo."""
    content = file_path.read_text(encoding="utf-8")
    content_hash = _sha256(content)
    filename = file_path.name

    async with AsyncSessionLocal() as db:
        # Buscar documento existente por filename
        doc_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.filename == filename,
            )
        )
        existing_doc = doc_result.scalar_one_or_none()

        # Skip si el hash coincide
        if existing_doc and existing_doc.content_hash == content_hash:
            return {"filename": filename, "chunks": 0, "tokens": 0, "skipped": True}

        # Generar chunks
        title = filename.removesuffix(".md").replace("_", " ").title()
        for line in content.splitlines():
            if line.startswith("# "):
                title = line.lstrip("#").strip()
                break

        chunks = split_with_overlap(content)
        chunk_texts = [c["text"] for c in chunks]
        total_tokens = sum(c["token_count"] for c in chunks)

        if dry_run:
            action = "actualizar" if existing_doc else "indexar"
            print(
                f"  [dry-run] {action} {filename}: "
                f"{len(chunks)} chunks, {total_tokens} tokens"
            )
            return {
                "filename": filename,
                "chunks": len(chunks),
                "tokens": total_tokens,
                "skipped": False,
            }

        # Generar embeddings (llamada síncrona OK en script)
        embeddings = generate_embeddings(openai_client, chunk_texts)

        # Upsert knowledge_document
        now = datetime.now(timezone.utc)
        if existing_doc:
            # Borrar chunks anteriores
            await db.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.document_id == existing_doc.id
                )
            )
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

        await db.flush()  # obtiene doc.id si es nuevo

        # Insertar chunks
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

    return {
        "filename": filename,
        "chunks": len(chunks),
        "tokens": total_tokens,
        "skipped": False,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Indexa la KB de Walix en pgvector")
    parser.add_argument(
        "--tenant-email", default="admin@clinica.com", help="Email del tenant"
    )
    parser.add_argument(
        "--branch-name", default=None, help="Nombre del branch (opcional)"
    )
    parser.add_argument(
        "--kb-dir",
        default=None,
        help="Directorio con archivos .md (default: walix_kb/ junto a este script)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué se indexaría sin escribir en la BD",
    )
    args = parser.parse_args()

    # Validar OPENAI_API_KEY
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        print(
            "ERROR: OPENAI_API_KEY no está configurado.\n"
            "Agrégalo a .env o como variable de entorno."
        )
        sys.exit(1)

    # Directorio de documentos
    kb_dir = Path(args.kb_dir) if args.kb_dir else Path(__file__).parent / "walix_kb"
    if not kb_dir.exists():
        print(f"ERROR: directorio '{kb_dir}' no existe.")
        sys.exit(1)

    md_files = sorted(kb_dir.glob("*.md"))
    if not md_files:
        print(f"No se encontraron archivos .md en '{kb_dir}'.")
        sys.exit(0)

    # Tenant y branch
    tenant_id, branch_id = await _find_tenant_and_branch(
        args.tenant_email, args.branch_name
    )

    openai_client = OpenAI(api_key=api_key)

    # Procesar archivos
    total_chunks = 0
    total_tokens = 0
    results: list[dict] = []

    print(
        f"Indexando {len(md_files)} archivo(s) desde '{kb_dir}'"
        + (" [dry-run]" if args.dry_run else "")
    )

    for file_path in md_files:
        result = await ingest_file(
            openai_client, file_path, tenant_id, branch_id, args.dry_run
        )
        results.append(result)

        if result["skipped"]:
            print(f"  → {result['filename']}: sin cambios (ya indexado)")
        else:
            label = "[dry-run] " if args.dry_run else ""
            print(
                f"  ✓ {label}{result['filename']}: "
                f"{result['chunks']} chunks indexados"
            )
            total_chunks += result["chunks"]
            total_tokens += result["tokens"]

    # Resumen
    indexed_docs = sum(1 for r in results if not r["skipped"])
    skipped_docs = sum(1 for r in results if r["skipped"])
    cost = total_tokens / 1_000_000 * EMBEDDING_PRICE_PER_1M

    print()
    parts = [f"Total: {indexed_docs} documento(s) indexado(s)"]
    if skipped_docs:
        parts.append(f"{skipped_docs} sin cambios")
    parts.append(f"{total_chunks} chunks")
    if not args.dry_run and total_tokens > 0:
        parts.append(f"estimado ${cost:.4f} USD en embeddings")
    print(", ".join(parts))


if __name__ == "__main__":
    asyncio.run(main())
