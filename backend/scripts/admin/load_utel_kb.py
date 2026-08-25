"""load_utel_kb.py — Paso 2 del Prompt Utel KB: carga los 88 documentos
(8 generales + 80 fichas de licenciatura normalizadas — ver nota abajo sobre
por qué 88 y no 87) al tenant Universidad Utel, vía el pipeline real de
embeddings (_embed_and_store, el mismo que usa create_document en
app/api/kb.py), llamado directo por función — NO por HTTP, script admin con
acceso directo a DB, mismo patrón que los demás scripts de Utel.

NOTA SOBRE EL CONTEO — 88, no 87:
El prompt asumía "82 PDFs originales con 3 duplicados exactos por hash =
79 fichas". Verificado con sha256 de cada PDF antes de escribir el parser:
81 PDFs presentes, y solo 1 par resultó ser un duplicado exacto por hash
(no 3) → 80 fichas únicas, no 79. 8 generales + 80 fichas = 88 documentos,
no 87. Ver normalize_licenciaturas.py para el detalle de la verificación.

Idempotente: si el tenant Utel ya tiene algún KnowledgeDocument con
is_auto_generated=False, aborta sin cargar nada (no intenta un merge
parcial — correr purge o revisar manualmente primero).

branch_id: KnowledgeDocument.branch_id es nullable (confirmado leyendo el
modelo) — pero se setea a la branch principal de Utel de todas formas, para
ser consistente con lo que hace create_document (app/api/kb.py) en uso real
vía REST (siempre usa current_user.branch_id).

filename: se usa el nombre real del .md fuente (ej. "04_sedes_horarios.md",
"mercadotecnia.md") en vez de un nombre sintético — esto es lo que permite
que la prueba de RAG del Paso 3 pueda confirmar que un resultado viene de un
documento específico por su filename.

Uso:
    .venv/Scripts/python.exe scripts/admin/load_utel_kb.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.kb import _embed_and_store, _sha256
from app.core.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeDocument
from app.models.tenant import Tenant
from app.services.tenant_setup import _find_principal_branch

UTEL_EMAIL = "admin@utel.walix.mx"
SOURCE_DIR = Path(__file__).resolve().parent / "utel_kb_source"
LICENCIATURAS_DIR = SOURCE_DIR / "03_licenciaturas"

GENERAL_DOCS = [
    "00_INDEX.md", "01_protocolo_perfilamiento.md", "02_modalidad_hibrida.md",
    "04_sedes_horarios.md", "05_manejo_objeciones.md", "06_mensajes_tipo.md",
    "07_preguntas_frecuentes.md", "08_admision_y_becas.md",
]
INDEX_TITLE_OVERRIDE = "Índice de Knowledge Base — Universidad Utel"


def _title_from_markdown(md_path: Path, content: str) -> str:
    if md_path.name == "00_INDEX.md":
        return INDEX_TITLE_OVERRIDE
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return md_path.stem


async def main() -> int:
    print("=" * 70)
    print("  load_utel_kb.py — Carga de Knowledge Base (Universidad Utel)")
    print("=" * 70)

    if not LICENCIATURAS_DIR.is_dir():
        print(f"\nNo existe {LICENCIATURAS_DIR} — correr normalize_licenciaturas.py primero.")
        return 1

    ficha_paths = sorted(LICENCIATURAS_DIR.glob("*.md"))
    general_paths = [SOURCE_DIR / name for name in GENERAL_DOCS]
    missing_general = [p for p in general_paths if not p.is_file()]
    if missing_general:
        print(f"\nFaltan documentos generales: {[p.name for p in missing_general]}")
        return 1

    all_paths = general_paths + ficha_paths
    print(f"\nDocumentos a cargar: {len(general_paths)} generales + {len(ficha_paths)} fichas = {len(all_paths)}")

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.email == UTEL_EMAIL))).scalar_one_or_none()
        if tenant is None:
            print(f"\nNo existe el tenant Utel ({UTEL_EMAIL!r}). Correr create_tenant_utel.py primero.")
            return 1

        branch = await _find_principal_branch(tenant.id, db)
        if branch is None:
            print(f"\nEl tenant Utel (id={tenant.id}) no tiene ninguna branch activa.")
            return 1

        # ── Idempotencia ──────────────────────────────────────────────────────
        existing_count = (await db.execute(
            select(func.count()).select_from(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant.id,
                KnowledgeDocument.is_auto_generated.is_(False),
            )
        )).scalar_one()
        if existing_count > 0:
            print(
                f"\nEl tenant Utel ya tiene {existing_count} documento(s) con "
                "is_auto_generated=False cargados — abortando, no se duplica nada. "
                "Este prompt no incluye un script de purga para la KB (a diferencia "
                "de Demo A/B) — borrar manualmente vía el Copiloto/UI o directo en BD "
                "si hace falta recargar."
            )
            return 1

        revisar_count = 0
        total_chunks = 0
        loaded = 0
        errors: list[str] = []

        for i, path in enumerate(all_paths, start=1):
            content = path.read_text(encoding="utf-8")
            title = _title_from_markdown(path, content)
            if content.lstrip().startswith("<!-- REVISAR"):
                revisar_count += 1

            content_hash = _sha256(content)
            doc_id = uuid.uuid4()
            now = datetime.now(timezone.utc)
            doc = KnowledgeDocument(
                id=doc_id,
                branch_id=branch.id,
                tenant_id=tenant.id,
                filename=path.name,
                title=title[:300],
                content=content,
                content_hash=content_hash,
                chunk_count=0,
                indexed_at=now,
                is_auto_generated=False,
            )
            db.add(doc)
            await db.flush()

            try:
                chunk_count = await _embed_and_store(content, doc_id, tenant.id, title, db)
            except HTTPException as exc:
                await db.rollback()
                errors.append(f"{path.name}: {exc.detail}")
                print(f"  ERROR {path.name}: {exc.detail}")
                continue

            doc.chunk_count = chunk_count
            await db.commit()
            total_chunks += chunk_count
            loaded += 1

            if i % 10 == 0 or i == len(all_paths):
                print(f"  [{i}/{len(all_paths)}] {path.name} → {chunk_count} chunks")

        print("\n✓ Carga completa\n")
        print(f"  Documentos cargados: {loaded}/{len(all_paths)}")
        print(f"  Chunks totales generados: {total_chunks}")
        print(f"  Fichas con <!-- REVISAR --> pendiente de revisión manual: {revisar_count}")
        if errors:
            print(f"\n  Errores ({len(errors)}):")
            for e in errors:
                print(f"    {e}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
