"""Hybrid retrieval for Walix RAG: vector search + BM25 fused with RRF.

retrieve_context()  — returns ranked chunks from knowledge_chunks
format_rag_context() — formats chunks as a Claude-ready context block

RRF score normalization
-----------------------
Raw RRF scores are tiny (~0–0.033) because the formula is 1/(k+rank+1).
We normalize by the theoretical maximum (2 * 1/(k+1), achieved when a chunk
ranks #0 in both searches) to produce a [0,1] score.

  normalized = raw_rrf / (2 / (RRF_K + 1))

With the default min_score=0.65, only chunks near the top of BOTH the vector
and BM25 rankings are included, ensuring high precision.
"""
import logging
import uuid

from openai import AsyncOpenAI
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 1536
RRF_K = 60
_MAX_RRF = 2.0 / (RRF_K + 1)   # ≈ 0.0328 — normalisation denominator

_openai: AsyncOpenAI | None = (
    AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    if settings.OPENAI_API_KEY
    else None
)

# ── SQL templates ──────────────────────────────────────────────────────────────

_VECTOR_SQL = text("""
    SELECT
        kc.id::text            AS id,
        kc.content             AS content,
        kc.metadata            AS metadata,
        kd.filename            AS filename,
        1 - (kc.embedding <=> CAST(:embedding AS vector)) AS score
    FROM knowledge_chunks kc
    JOIN knowledge_documents kd ON kc.document_id = kd.id
    WHERE kc.tenant_id = CAST(:tenant_id AS uuid)
    ORDER BY kc.embedding <=> CAST(:embedding AS vector)
    LIMIT 10
""")

_BM25_SQL = text("""
    SELECT
        kc.id::text            AS id,
        kc.content             AS content,
        kc.metadata            AS metadata,
        kd.filename            AS filename,
        ts_rank(
            to_tsvector('spanish', kc.content),
            plainto_tsquery('spanish', :query)
        )                      AS score
    FROM knowledge_chunks kc
    JOIN knowledge_documents kd ON kc.document_id = kd.id
    WHERE kc.tenant_id = CAST(:tenant_id AS uuid)
      AND to_tsvector('spanish', kc.content) @@ plainto_tsquery('spanish', :query)
    ORDER BY score DESC
    LIMIT 10
""")


# ── Public API ─────────────────────────────────────────────────────────────────

async def retrieve_context(
    query: str,
    tenant_id: str,
    top_k: int = 3,
    min_score: float = 0.45,
) -> list[dict]:
    """Hybrid vector + BM25 retrieval fused with Reciprocal Rank Fusion.

    Returns up to *top_k* dicts with keys:
        id, content, metadata, filename, rrf_score
    Chunks with normalised RRF score < min_score are excluded.
    Returns [] when OpenAI is not configured or no chunks pass the filter.
    """
    if _openai is None:
        logger.warning("retrieve_context: OPENAI_API_KEY not set — skipping RAG")
        return []

    # 1. Embed the query
    emb_response = await _openai.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
        dimensions=EMBEDDING_DIMS,
    )
    query_vector: list[float] = emb_response.data[0].embedding
    embedding_str = "[" + ",".join(f"{x:.8f}" for x in query_vector) + "]"
    tenant_str = str(tenant_id)

    async with AsyncSessionLocal() as db:
        # 2. Vector search
        vec_rows = (
            await db.execute(
                _VECTOR_SQL, {"embedding": embedding_str, "tenant_id": tenant_str}
            )
        ).mappings().all()

        # 3. BM25 search
        bm25_rows = (
            await db.execute(
                _BM25_SQL, {"query": query, "tenant_id": tenant_str}
            )
        ).mappings().all()

    # 4. Build lookup: chunk_id → row data
    chunks: dict[str, dict] = {}
    for row in [*vec_rows, *bm25_rows]:
        cid = row["id"]
        if cid not in chunks:
            chunks[cid] = {
                "id": cid,
                "content": row["content"],
                "metadata": dict(row["metadata"]) if row["metadata"] else {},
                "filename": row["filename"],
                "rrf_score": 0.0,
            }

    # 5. RRF fusion — accumulate 1/(k + rank + 1) from each ranked list
    for rank, row in enumerate(vec_rows):
        chunks[row["id"]]["rrf_score"] += 1.0 / (RRF_K + rank + 1)

    for rank, row in enumerate(bm25_rows):
        chunks[row["id"]]["rrf_score"] += 1.0 / (RRF_K + rank + 1)

    # 6. Normalise to [0, 1]
    for c in chunks.values():
        c["rrf_score"] = round(c["rrf_score"] / _MAX_RRF, 4)

    # 7. Sort descending, take top_k, filter by min_score
    ranked = sorted(chunks.values(), key=lambda c: c["rrf_score"], reverse=True)
    results = [c for c in ranked[:top_k] if c["rrf_score"] >= min_score]

    if not results:
        logger.info(
            "retrieve_context: no chunks above min_score=%.2f for query=%r",
            min_score, query[:60],
        )

    return results


def format_rag_context(chunks: list[dict]) -> str:
    """Formats retrieved chunks as a context block for Claude.

    Returns an empty string when chunks is empty (no context injected).
    """
    if not chunks:
        return ""

    lines = ["INFORMACIÓN DE LA CLÍNICA (usa SOLO esta información, no inventes):"]

    for i, chunk in enumerate(chunks, start=1):
        score = chunk.get("rrf_score", 0)
        filename = chunk.get("filename", "fuente desconocida")
        content = chunk.get("content", "").strip()
        lines.append(f"\n[{i}] (score: {score:.2f} · fuente: {filename})")
        lines.append(f'"{content}"')

    lines.append(
        "\nSi la respuesta no está en esta información, di: "
        "'No tengo esa información específica, pero una de nuestras "
        "especialistas puede ayudarte mejor. ¿Te la conecto?'"
    )

    return "\n".join(lines)
