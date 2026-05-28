import logging
import uuid

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 1536
DEFAULT_TOP_K = 4
DEFAULT_MIN_SIMILARITY = 0.65

# Client is None when OPENAI_API_KEY is not configured (local dev without RAG).
_openai: AsyncOpenAI | None = (
    AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    if settings.OPENAI_API_KEY
    else None
)


async def retrieve_context(
    query: str,
    tenant_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = DEFAULT_TOP_K,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> list[dict]:
    """Busca los chunks más relevantes para el query usando similitud coseno.

    Retorna lista de dicts {content, section, document_title, similarity}.
    Retorna lista vacía si OpenAI no está configurado o si no hay chunks relevantes.
    """
    if _openai is None:
        return []

    # 1. Embedding del query del usuario
    response = await _openai.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
        dimensions=EMBEDDING_DIMS,
    )
    query_vector: list[float] = response.data[0].embedding

    # 2. Búsqueda por similitud coseno en pgvector.
    #    cosine_distance = 1 - cosine_similarity, así que
    #    distance <= (1 - min_similarity) equivale a similarity >= min_similarity.
    distance_threshold = 1.0 - min_similarity
    distance_col = KnowledgeChunk.embedding.cosine_distance(query_vector)

    stmt = (
        select(
            KnowledgeChunk.content,
            KnowledgeChunk.chunk_metadata,
            KnowledgeDocument.title,
            (1 - distance_col).label("similarity"),
        )
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeChunk.tenant_id == tenant_id,
            distance_col <= distance_threshold,
        )
        .order_by(distance_col)
        .limit(top_k)
    )

    rows = await db.execute(stmt)

    return [
        {
            "content": row.content,
            "section": (row.chunk_metadata or {}).get("section", ""),
            "document_title": row.title,
            "similarity": round(float(row.similarity), 3),
        }
        for row in rows
    ]
