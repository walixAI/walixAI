"""test_utel_kb.py — Verificación de la carga completa de Knowledge Base de
Universidad Utel (88 documentos: 8 generales + 80 fichas de licenciatura —
ver load_utel_kb.py para la nota sobre por qué 88 y no 87).

Verificaciones:
  a) 88 documentos para el tenant Utel, ninguno duplicado por filename.
  b) Cada uno tiene chunk_count > 0 (embeddings reales generados).
  c) Ningún documento excede title(255)/content(20000) — límites reales de
     app/api/kb.py::DocumentIn (Pydantic), no los de la columna de BD (que
     son más laxos: title es String(300) a nivel de columna).
  d) Búsqueda RAG real de punta a punta con app/ai/retrieval.py::
     retrieve_context (la función REAL que bot_engine.py usa en producción,
     confirmado en el Paso 0 — NO app/services/rag.py, que no está
     importado en ningún lado del código real) — query "modalidad híbrida
     sede Monterrey", reporta el resultado real para que Walix lo evalúe
     (no es un PASS/FAIL estricto per el propio prompt).
  e) Lista cuántas fichas quedaron con <!-- REVISAR --> (informativo, no FAIL).
  f) PASS/FAIL por cada verificación.

Uso:
    .venv/Scripts/python.exe scripts/test_utel_kb.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.ai.retrieval import retrieve_context
from app.core.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeDocument
from app.models.tenant import Tenant

UTEL_EMAIL = "admin@utel.walix.mx"
EXPECTED_TOTAL = 88


async def main() -> int:
    print("=" * 70)
    print("  test_utel_kb.py — Knowledge Base de Universidad Utel (88 docs)")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.email == UTEL_EMAIL))).scalar_one_or_none()
        if tenant is None:
            print(f"\nNo existe el tenant Utel ({UTEL_EMAIL!r}).")
            return 1

        docs = (await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant.id,
                KnowledgeDocument.is_auto_generated.is_(False),
            )
        )).scalars().all()

        # ── a) 88 documentos, sin filename duplicado ─────────────────────────
        filenames = [d.filename for d in docs]
        dup_filenames = {f for f in filenames if filenames.count(f) > 1}
        ok_a = len(docs) == EXPECTED_TOTAL and not dup_filenames
        results.append((
            f"a. {EXPECTED_TOTAL} documentos para Utel, ningún filename duplicado",
            ok_a,
            f"total={len(docs)} duplicados={dup_filenames}",
        ))

        # ── b) chunk_count > 0 en todos ───────────────────────────────────────
        zero_chunk = [d.filename for d in docs if d.chunk_count <= 0]
        ok_b = len(zero_chunk) == 0
        results.append((
            "b. Todos los documentos tienen chunk_count > 0",
            ok_b,
            f"con_chunk_count<=0={zero_chunk}",
        ))

        # ── c) límites title(255)/content(20000) ──────────────────────────────
        over_title = [d.filename for d in docs if len(d.title) > 255]
        over_content = [d.filename for d in docs if d.content and len(d.content) > 20_000]
        ok_c = not over_title and not over_content
        results.append((
            "c. Ningún documento excede title(255)/content(20000)",
            ok_c,
            f"title_excedido={over_title} content_excedido={over_content}",
        ))

        # ── e) conteo de REVISAR ──────────────────────────────────────────────
        revisar_docs = [d.filename for d in docs if (d.content or "").lstrip().startswith("<!-- REVISAR")]

    # ── d) búsqueda RAG real de punta a punta ─────────────────────────────────
    # retrieve_context abre su propia sesión internamente (app/ai/retrieval.py),
    # no hace falta pasarle una acá.
    query = "modalidad híbrida sede Monterrey"
    rag_chunks = await retrieve_context(query, str(tenant.id))
    rag_filenames = [c.get("filename") for c in rag_chunks]
    # Criterio simple y directo: ¿algún resultado viene de 04_sedes_horarios.md
    # o de una ficha de licenciatura (cualquier .md que no sea uno de los 8
    # generales, es decir no empieza con 0 seguido de _ y 2 dígitos conocidos)?
    general_filenames = {
        "00_INDEX.md", "01_protocolo_perfilamiento.md", "02_modalidad_hibrida.md",
        "04_sedes_horarios.md", "05_manejo_objeciones.md", "06_mensajes_tipo.md",
        "07_preguntas_frecuentes.md", "08_admision_y_becas.md",
    }
    rag_hit = any(
        f == "04_sedes_horarios.md" or (f is not None and f not in general_filenames)
        for f in rag_filenames
    )
    print()
    print(f"  [FUNCIONAL] d. Búsqueda RAG real — query={query!r}")
    print(f"              chunks_retornados={len(rag_chunks)}")
    for c in rag_chunks:
        print(f"                - filename={c.get('filename')!r} rrf_score={c.get('rrf_score')} content_preview={c.get('content', '')[:100]!r}")
    print(f"              ¿algún resultado de 04_sedes_horarios.md o de una ficha?: {rag_hit}")
    print("              (no es PASS/FAIL estricto por diseño del prompt — reportado para que Walix lo evalúe)")

    return _report(results, revisar_docs)


def _report(results: list[tuple[str, bool, str]], revisar_docs: list[str]) -> int:
    print()
    all_ok = True
    for label, ok, detail in results:
        tag = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{tag}] {label}\n         {detail}")
    print(f"\n  [INFO] e. Fichas con <!-- REVISAR --> pendiente ({len(revisar_docs)}):")
    for f in revisar_docs:
        print(f"         {f}")
    print()
    if all_ok:
        print("✓ Todas las verificaciones PASS/FAIL pasaron (ver arriba el resultado funcional de RAG y el conteo de REVISAR).")
        return 0
    print("✗ Al menos una verificación falló — ver detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
