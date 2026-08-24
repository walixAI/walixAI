"""test_kb_wireo.py — Verificación del wireo completo de Knowledge Base
(app/api/kb.py) al catálogo del Copiloto: 9 acciones
(reindex_kb, kb_status, list_kb_documents, get_kb_document,
create_kb_document, update_kb_document, delete_kb_document,
add_kb_fragment, delete_kb_fragment).

Llama execute_tool() directo (mismo patrón que
scripts/diagnostics/test_finanzas_ronda2a_*.py) contra un tenant desechable
propio, creado y limpiado en esta misma corrida.

ENFOQUE DE OPENAI: mock/monkeypatch de app.api.kb._generate_embeddings
(devuelve vectores dummy de dimensión 1536), NO llamadas reales — evita
depender de la red/cuota de OpenAI y hace la corrida determinística y
rápida. _embed_and_store (app/api/kb.py) resuelve `_generate_embeddings`
como global de su propio módulo en tiempo de llamada, así que parchear
app.api.kb._generate_embeddings alcanza (sin importar que
copilot_tools.py haya importado _embed_and_store directo). OPENAI_API_KEY
sigue necesitando estar configurado en settings (aunque sea un valor
dummy) porque _embed_and_store chequea su presencia antes de llegar a
_generate_embeddings.

Verificaciones:
  a) create_kb_document crea el doc con chunks generados; aparece en
     list_kb_documents y kb_status.
  b) create_kb_document con el MISMO content (mismo hash) -> retorna el
     existente, no crea un segundo documento ni regenera embeddings.
  c) update_kb_document cambia solo el title -> chunk_count/content/chunks
     NO cambian (hash de content sin cambios).
  d) update_kb_document cambia el content -> chunk_count puede cambiar,
     los KnowledgeChunk viejos ya no existen (reemplazados, no acumulados).
  e) delete_kb_document sobre un doc normal (is_auto_generated=False) ->
     borra directo, sin pedir confirmación.
  f) delete_kb_document sobre un doc con is_auto_generated=True, sin
     confirm -> NO borra, retorna requires_confirmation=True; el doc sigue
     existiendo.
  g) mismo doc de (f), reintentando con confirm=True -> SÍ borra.
  h) delete_kb_fragment sobre un doc is_auto_generated=True (sin pasar
     confirm, la acción ni lo acepta) -> borra directo (asimetría real del
     alias legacy, sin guardrail).
  i) get_kb_document sobre un doc file-based (content=None en la fila,
     solo con chunks) -> reconstruye el contenido concatenando chunks en
     orden.
  j) Usuario con rol ASESOR (fuera de todos los conjuntos de KB) ->
     kb_status (lectura) y create_kb_document (escritura) denegados.

Uso:
    .venv/Scripts/python.exe scripts/diagnostics/test_kb_wireo.py
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

from sqlalchemy import delete, select

import app.api.kb as kb_module
from app.ai.copilot_tools import execute_tool
from app.core.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole

_DUMMY_VECTOR = [0.001] * 1536


async def _fake_generate_embeddings(client, texts: list[str]) -> list[list[float]]:
    return [_DUMMY_VECTOR for _ in texts]


# Monkeypatch — ver docstring del módulo arriba.
kb_module._generate_embeddings = _fake_generate_embeddings


async def _setup() -> dict:
    async with AsyncSessionLocal() as db:
        tag = uuid.uuid4().hex[:8]

        tenant = Tenant(
            name=f"[test_kb_wireo] {tag}",
            email=f"kbwireo-{tag}@walix.test",
            plan=TenantPlan.STARTER,
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

        company = Company(tenant_id=tenant.id, name="Empresa Test")
        db.add(company)
        await db.flush()

        branch = Branch(company_id=company.id, tenant_id=tenant.id, name="Sucursal", is_active=True)
        db.add(branch)
        await db.flush()

        owner_user = User(
            tenant_id=tenant.id, branch_id=branch.id,
            email=f"owner-{tag}@walix.test", name="Owner Test",
            hashed_password="not-used", role=UserRole.OWNER, is_active=True,
        )
        db.add(owner_user)

        asesor_no_permission = User(
            tenant_id=tenant.id, branch_id=branch.id,
            email=f"asesor-noperm-{tag}@walix.test", name="Asesor Sin Acceso",
            hashed_password="not-used", role=UserRole.ASESOR, is_active=True,
        )
        db.add(asesor_no_permission)
        await db.flush()
        await db.commit()

        return {
            "tenant": tenant,
            "tenant_id": tenant.id,
            "owner_user": owner_user,
            "asesor_no_permission": asesor_no_permission,
        }


async def _cleanup(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tenant).where(Tenant.id == ctx["tenant_id"]))
        await db.commit()


async def _count_docs(tenant_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == tenant_id)
        )).scalars().all()
        return len(rows)


async def _chunk_ids(doc_id: uuid.UUID) -> set[uuid.UUID]:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(KnowledgeChunk.id).where(KnowledgeChunk.document_id == doc_id)
        )).scalars().all()
        return set(rows)


async def _doc_exists(doc_id: uuid.UUID) -> bool:
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        )).scalar_one_or_none()
        return row is not None


async def main() -> int:
    print("=" * 70)
    print("  test_kb_wireo.py — Knowledge Base (9 acciones)")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []
    ctx = await _setup()

    try:
        tenant = ctx["tenant"]
        owner = ctx["owner_user"]
        asesor_no_permission = ctx["asesor_no_permission"]
        tenant_id = ctx["tenant_id"]

        async with AsyncSessionLocal() as db:
            # ── a) create_kb_document + aparece en list/kb_status ────────────
            content_a = "Este es el contenido de prueba del documento A. " * 5
            created_a = await execute_tool(
                "create_kb_document",
                {"title": "Doc A", "content": content_a},
                owner, tenant, db,
            )
            doc_a_id = created_a.get("id")
            ok_a = "error" not in created_a and doc_a_id is not None and created_a.get("chunk_count", 0) > 0
            if ok_a:
                listed = await execute_tool("list_kb_documents", {}, owner, tenant, db)
                status = await execute_tool("kb_status", {}, owner, tenant, db)
                ok_a = (
                    isinstance(listed, list) and any(d.get("id") == doc_a_id for d in listed)
                    and "error" not in status
                    and status.get("total_documents", 0) >= 1
                    and status.get("total_chunks", 0) >= created_a.get("chunk_count", 0)
                )
            results.append((
                "a. create_kb_document crea el doc con chunks, aparece en list_kb_documents y kb_status",
                ok_a, f"created={created_a}",
            ))
            if not ok_a:
                results.append(("ABORTADO — sin doc_a_id válido no se puede seguir", False, "ver punto a arriba"))
                return _report(results)

            # ── b) mismo content -> idempotente, NO crea un segundo doc ──────
            docs_before_b = await _count_docs(tenant_id)
            dup_b = await execute_tool(
                "create_kb_document",
                {"title": "Doc A (otro título)", "content": content_a},
                owner, tenant, db,
            )
            docs_after_b = await _count_docs(tenant_id)
            ok_b = (
                "error" not in dup_b and dup_b.get("id") == doc_a_id
                and docs_after_b == docs_before_b
            )
            results.append((
                "b. create_kb_document con mismo content -> retorna el existente, no duplica",
                ok_b, f"dup={dup_b} docs_before={docs_before_b} docs_after={docs_after_b}",
            ))

            # ── c) update_kb_document solo title -> content/chunks intactos ──
            chunks_before_c = await _chunk_ids(doc_a_id)
            updated_c = await execute_tool(
                "update_kb_document",
                {"doc_id": doc_a_id, "title": "Doc A Renombrado"},
                owner, tenant, db,
            )
            chunks_after_c = await _chunk_ids(doc_a_id)
            got_c = await execute_tool("get_kb_document", {"doc_id": doc_a_id}, owner, tenant, db)
            ok_c = (
                "error" not in updated_c
                and updated_c.get("title") == "Doc A Renombrado"
                and updated_c.get("chunk_count") == created_a.get("chunk_count")
                and chunks_before_c == chunks_after_c  # no se tocaron los chunks
                and got_c.get("content") == content_a  # contenido intacto
            )
            results.append((
                "c. update_kb_document (solo title) NO regenera embeddings ni cambia content",
                ok_c, f"updated={updated_c} chunks_before={len(chunks_before_c)} chunks_after={len(chunks_after_c)}",
            ))

            # ── d) update_kb_document cambia content -> chunks reemplazados ──
            chunks_before_d = await _chunk_ids(doc_a_id)
            new_content_d = "Contenido totalmente distinto para forzar regeneración. " * 8
            updated_d = await execute_tool(
                "update_kb_document",
                {"doc_id": doc_a_id, "content": new_content_d},
                owner, tenant, db,
            )
            chunks_after_d = await _chunk_ids(doc_a_id)
            ok_d = (
                "error" not in updated_d
                and updated_d.get("chunk_count", 0) > 0
                and chunks_before_d.isdisjoint(chunks_after_d)  # viejos reemplazados, no acumulados
                and len(chunks_after_d) == updated_d.get("chunk_count")
            )
            results.append((
                "d. update_kb_document (content) regenera chunks — viejos reemplazados, no acumulados",
                ok_d, f"updated={updated_d} chunks_before={len(chunks_before_d)} chunks_after={len(chunks_after_d)}",
            ))

            # ── e) delete_kb_document normal -> borra directo ────────────────
            created_e = await execute_tool(
                "create_kb_document",
                {"title": "Doc E temporal", "content": "Contenido temporal para borrar de inmediato. " * 3},
                owner, tenant, db,
            )
            doc_e_id = created_e.get("id")
            deleted_e = await execute_tool("delete_kb_document", {"doc_id": doc_e_id}, owner, tenant, db) if doc_e_id else {}
            exists_after_e = await _doc_exists(doc_e_id) if doc_e_id else True
            ok_e = (
                doc_e_id is not None
                and deleted_e.get("deleted") is True
                and not exists_after_e
            )
            results.append((
                "e. delete_kb_document sobre doc normal -> borra directo, sin confirmación",
                ok_e, f"created={created_e} deleted={deleted_e}",
            ))

            # ── f/g) delete_kb_document sobre doc auto_generated ─────────────
            now = datetime.now(timezone.utc)
            doc_fg_id = uuid.uuid4()
            auto_doc = KnowledgeDocument(
                id=doc_fg_id, tenant_id=tenant_id, branch_id=owner.branch_id,
                filename=f"auto_{doc_fg_id.hex[:8]}.txt", title="Doc Auto-generado",
                content="Contenido auto-generado desde onboarding.", content_hash=f"hash-{doc_fg_id.hex}",
                chunk_count=0, indexed_at=now, is_auto_generated=True,
            )
            db.add(auto_doc)
            await db.commit()

            no_confirm_f = await execute_tool("delete_kb_document", {"doc_id": doc_fg_id}, owner, tenant, db)
            exists_after_f = await _doc_exists(doc_fg_id)
            ok_f = (
                "error" not in no_confirm_f
                and no_confirm_f.get("requires_confirmation") is True
                and no_confirm_f.get("doc_id") == str(doc_fg_id)
                and exists_after_f
            )
            results.append((
                "f. delete_kb_document sobre doc auto_generated sin confirm -> requires_confirmation, no borra",
                ok_f, f"result={no_confirm_f} exists_after={exists_after_f}",
            ))

            confirmed_g = await execute_tool(
                "delete_kb_document", {"doc_id": doc_fg_id, "confirm": True}, owner, tenant, db,
            )
            exists_after_g = await _doc_exists(doc_fg_id)
            ok_g = confirmed_g.get("deleted") is True and not exists_after_g
            results.append((
                "g. delete_kb_document mismo doc con confirm=True -> SÍ borra",
                ok_g, f"result={confirmed_g} exists_after={exists_after_g}",
            ))

            # ── h) delete_kb_fragment sobre doc auto_generated -> sin guardrail ──
            doc_h_id = uuid.uuid4()
            auto_doc_h = KnowledgeDocument(
                id=doc_h_id, tenant_id=tenant_id, branch_id=owner.branch_id,
                filename=f"auto_{doc_h_id.hex[:8]}.txt", title="Doc Auto-generado 2",
                content="Otro contenido auto-generado.", content_hash=f"hash-{doc_h_id.hex}",
                chunk_count=0, indexed_at=now, is_auto_generated=True,
            )
            db.add(auto_doc_h)
            await db.commit()

            deleted_h = await execute_tool("delete_kb_fragment", {"document_id": doc_h_id}, owner, tenant, db)
            exists_after_h = await _doc_exists(doc_h_id)
            ok_h = deleted_h.get("deleted") is True and not exists_after_h
            results.append((
                "h. delete_kb_fragment sobre doc auto_generated -> borra directo (sin guardrail, asimetría real)",
                ok_h, f"result={deleted_h} exists_after={exists_after_h}",
            ))

            # ── i) get_kb_document file-based (content=None + chunks) ────────
            doc_i_id = uuid.uuid4()
            file_doc = KnowledgeDocument(
                id=doc_i_id, tenant_id=tenant_id, branch_id=owner.branch_id,
                filename="archivo_test.md", title="Doc File-Based",
                content=None, content_hash=f"hash-{doc_i_id.hex}",
                chunk_count=2, indexed_at=now, is_auto_generated=False,
            )
            db.add(file_doc)
            await db.flush()
            db.add(KnowledgeChunk(
                id=uuid.uuid4(), document_id=doc_i_id, tenant_id=tenant_id,
                chunk_index=1, content="Segundo fragmento.", embedding=_DUMMY_VECTOR,
                token_count=3, chunk_metadata={},
            ))
            db.add(KnowledgeChunk(
                id=uuid.uuid4(), document_id=doc_i_id, tenant_id=tenant_id,
                chunk_index=0, content="Primer fragmento.", embedding=_DUMMY_VECTOR,
                token_count=2, chunk_metadata={},
            ))
            await db.commit()

            got_i = await execute_tool("get_kb_document", {"doc_id": doc_i_id}, owner, tenant, db)
            ok_i = (
                "error" not in got_i
                and got_i.get("content") == "Primer fragmento.\n\nSegundo fragmento."
            )
            results.append((
                "i. get_kb_document (file-based, content=None) reconstruye desde chunks en orden",
                ok_i, f"result={got_i}",
            ))

            # ── j) ASESOR (fuera de todos los conjuntos de KB) -> denegado ───
            denied_read_j = await execute_tool("kb_status", {}, asesor_no_permission, tenant, db)
            docs_before_j = await _count_docs(tenant_id)
            denied_write_j = await execute_tool(
                "create_kb_document",
                {"title": "No debería crearse", "content": "Contenido que no debería indexarse. " * 3},
                asesor_no_permission, tenant, db,
            )
            docs_after_j = await _count_docs(tenant_id)
            ok_j = (
                "error" in denied_read_j
                and "error" in denied_write_j
                and docs_after_j == docs_before_j
            )
            results.append((
                "j. Usuario ASESOR denegado en kb_status (lectura) y create_kb_document (escritura)",
                ok_j, f"read={denied_read_j} write={denied_write_j}",
            ))

        return _report(results)

    finally:
        await _cleanup(ctx)
        print("\n(datos de prueba limpiados)")


def _report(results: list[tuple[str, bool, str]]) -> int:
    print()
    all_ok = True
    for label, ok, detail in results:
        tag = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{tag}] {label}\n         {detail}")
    print()
    if all_ok:
        print("✓ Todas las verificaciones pasaron.")
        return 0
    print("✗ Al menos una verificación falló — ver detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
