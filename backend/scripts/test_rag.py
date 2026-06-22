"""Prueba el retrieval híbrido (vector + BM25 + RRF) contra la BD local.

Corre desde backend/:
    .venv/bin/python scripts/test_rag.py

Requiere OPENAI_API_KEY en .env y la KB ya indexada (scripts/ingest_kb.py).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

from sqlalchemy import select

from app.ai.retrieval import retrieve_context
from app.core.database import AsyncSessionLocal
from app.models.tenant import Tenant

TENANT_EMAIL = "admin@clinica.com"

QUERIES = [
    "cuántos años debe tener el niño para calificar",
    "el tratamiento tiene efectos secundarios",
    "estoy en Santa Fe Ciudad de México",
    "ya fui con otro médico y me dijeron que está bien",
    "cuánto cuesta la consulta",
]


async def get_tenant_id() -> str:
    async with AsyncSessionLocal() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.email == TENANT_EMAIL))
        ).scalar_one_or_none()
        if tenant is None:
            print(f"ERROR: tenant '{TENANT_EMAIL}' no encontrado. Corre seed.py primero.")
            sys.exit(1)
        return str(tenant.id)


async def run() -> int:
    tenant_id = await get_tenant_id()
    print(f"Tenant: {TENANT_EMAIL}  ({tenant_id})\n")
    print("=" * 70)

    failures = 0
    for query in QUERIES:
        chunks = await retrieve_context(query, tenant_id)
        retrieved = len(chunks)
        ok = retrieved > 0
        tag = "✓" if ok else "✗"
        if not ok:
            failures += 1
        print(f"\n{tag} Query: {query!r}")
        print(f"  Fragmentos recuperados: {retrieved}")
        for i, c in enumerate(chunks, start=1):
            preview = c["content"].replace("\n", " ")[:100]
            print(f"  [{i}] score: {c['rrf_score']:.2f} · fuente: {c['filename']}")
            print(f"       {preview}…")

    print("\n" + "=" * 70)
    if failures:
        print(f"✗ {failures}/{len(QUERIES)} queries retornaron 0 fragmentos — revisar KB indexado.")
    else:
        print(f"✓ Todos los {len(QUERIES)} queries retornaron resultados.")
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
