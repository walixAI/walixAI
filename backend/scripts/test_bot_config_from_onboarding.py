"""test_bot_config_from_onboarding.py — Sprint 12: verifica que el onboarding
genera la config del bot y el documento KB inicial automáticamente.

Checks:
  a) Onboarding analyze + confirm → bot_config_generated=true, campos no null
  b) GET /api/branches/{id}/bot-config → campos persistidos, is_auto_generated=true
  c) GET /api/kb/documents → existe al menos 1 doc con is_auto_generated=true
  d) PATCH bot-config → bot_config_updated_at se actualiza, cambio persiste
  e) POST bot-config/regenerate → retorna nueva config, generated_at se actualiza
  f) POST/GET/PATCH/DELETE /api/kb/documents → CRUD completo funciona
  g) Limpieza de datos de prueba creados en este script

NOTA: los checks a) y e) llaman a Claude (10-20s cada uno). El script puede
tardar ~60 segundos en total.

Uso:
  cd backend
  .venv/bin/python scripts/test_bot_config_from_onboarding.py
  .venv/bin/python scripts/test_bot_config_from_onboarding.py --email owner@clinica.com --password walix2026
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = "http://localhost:8000"

_PASS = "✓ PASS"
_FAIL = "✗ FAIL"
_SKIP = "– SKIP"

# En CI (APP_ENV=test o sin ANTHROPIC_API_KEY) se omiten checks que llaman a Claude
import os as _os
CI_MODE = _os.environ.get("APP_ENV") == "test" or not _os.environ.get("ANTHROPIC_API_KEY")

failures: list[str] = []
_created_doc_ids: list[str] = []          # KB docs created during the test
_original_bot_config: dict | None = None  # saved before modifications


def report(label: str, ok: bool | None, detail: str = "") -> None:
    tag = _PASS if ok is True else (_FAIL if ok is False else _SKIP)
    if ok is False:
        failures.append(label)
    line = f"  {tag}  {label}"
    if detail:
        line += f"\n         {detail}"
    print(line)


def get_args() -> tuple[str, str]:
    args = sys.argv[1:]
    email, password = "owner@clinica.com", "walix2026"
    for i, a in enumerate(args):
        if a == "--email" and i + 1 < len(args):
            email = args[i + 1]
        elif a == "--password" and i + 1 < len(args):
            password = args[i + 1]
    return email, password


def login(client: httpx.Client, email: str, password: str) -> str | None:
    try:
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        if r.status_code == 200:
            return r.json()["access_token"]
    except Exception as exc:
        print(f"  {_FAIL}  LOGIN: {exc}")
    return None


def get_branch_id(client: httpx.Client, token: str) -> str | None:
    """Returns the first branch_id accessible to the user."""
    try:
        r = client.get("/api/branches", headers={"Authorization": f"Bearer {token}"})
        branches = r.json()
        if branches:
            # Prefer the one named 'Monterrey' or any principal
            for b in branches:
                if "monterrey" in b["name"].lower() or "principal" in b["name"].lower():
                    return b["id"]
            return branches[0]["id"]
    except Exception:
        pass
    return None


# ── Check (a) — Onboarding analyze + confirm ─────────────────────────────────

def check_a(client: httpx.Client, token: str) -> dict | None:
    """Simulates the onboarding flow and verifies bot_config_generated=true."""
    auth = {"Authorization": f"Bearer {token}"}

    # Step 1: analyze
    desc = (
        "Tenemos una clínica de endocrinología pediátrica. Atendemos niños con "
        "problemas de diabetes, tiroides y crecimiento. Somos 3 médicos y 2 "
        "recepcionistas. Usamos WhatsApp para captar pacientes nuevos."
    )
    r = client.post("/api/v1/onboarding/analyze", json={"description": desc})
    ok_analyze = r.status_code == 200 and "industry_key" in r.json()
    report("(a.1) POST /v1/onboarding/analyze → 200 con industry_key",
           ok_analyze, f"status={r.status_code}")
    if not ok_analyze:
        return None

    industry_key = r.json().get("industry_key") or "salud"

    # Step 2: confirm (triggers Claude bot config generation — may take ~15s)
    if CI_MODE:
        report("(a.2) POST /v1/onboarding/confirm (omitido en CI — sin ANTHROPIC_API_KEY)", None)
        report("(a.3) bot_config_generated", None, "omitido en CI")
        report("(a.4) bot_config.system_prompt", None, "omitido en CI")
        report("(a.5) bot_config.tone", None, "omitido en CI")
        report("(a.6) bot_config.qualification_questions", None, "omitido en CI")
        return None
    print("        ↳ Llamando a confirm + Claude (puede tardar ~15s)…")
    t0 = time.monotonic()
    r2 = client.post(
        "/api/v1/onboarding/confirm",
        json={"description": desc, "industry_key": industry_key},
        headers=auth,
    )
    elapsed = round(time.monotonic() - t0, 1)
    ok_confirm = r2.status_code == 200
    report(f"(a.2) POST /v1/onboarding/confirm → 200 ({elapsed}s)",
           ok_confirm, f"status={r2.status_code}")
    if not ok_confirm:
        return None

    data = r2.json()
    bot_gen = data.get("bot_config_generated") is True
    report("(a.3) bot_config_generated = true", bot_gen,
           f"bot_config_generated={data.get('bot_config_generated')}")

    bc = data.get("bot_config") or {}
    has_prompt    = bool(bc.get("system_prompt"))
    has_tone      = bc.get("tone") in ("formal", "amigable", "profesional", "cercano")
    has_questions = isinstance(bc.get("qualification_questions"), list) and len(bc["qualification_questions"]) >= 3

    report("(a.4) bot_config.system_prompt presente", has_prompt,
           f"chars={len(bc.get('system_prompt') or '')}")
    report("(a.5) bot_config.tone válido", has_tone,
           f"tone={bc.get('tone')}")
    report("(a.6) bot_config.qualification_questions (≥3)", has_questions,
           f"count={len(bc.get('qualification_questions') or [])}")

    return data


# ── Check (b) — Persistencia en branch ───────────────────────────────────────

def check_b(client: httpx.Client, token: str, branch_id: str) -> dict | None:
    global _original_bot_config
    auth = {"Authorization": f"Bearer {token}"}

    r = client.get(f"/api/branches/{branch_id}/bot-config", headers=auth)
    ok = r.status_code == 200
    report("(b.1) GET /branches/{id}/bot-config → 200", ok, f"status={r.status_code}")
    if not ok:
        return None

    cfg = r.json()
    _original_bot_config = cfg  # save for cleanup

    ok_prompt    = bool(cfg.get("system_prompt"))
    ok_tone      = bool(cfg.get("tone"))
    ok_questions = isinstance(cfg.get("qualification_questions"), list) and len(cfg["qualification_questions"]) > 0
    ok_auto      = cfg.get("is_auto_generated") is True

    if CI_MODE:
        # (a.2) confirm quedó skipeado — nunca se generó bot_config, así que
        # b.2/b.3/b.4 fallarían siempre por diseño, no por un bug real.
        report("(b.2) system_prompt persistido", None, "omitido en CI (confirm skipped)")
        report("(b.3) tone persistido", None, "omitido en CI (confirm skipped)")
        report("(b.4) qualification_questions persistidas", None, "omitido en CI (confirm skipped)")
    else:
        report("(b.2) system_prompt persistido", ok_prompt,
               f"chars={len(cfg.get('system_prompt') or '')}")
        report("(b.3) tone persistido", ok_tone, f"tone={cfg.get('tone')}")
        report("(b.4) qualification_questions persistidas", ok_questions,
               f"count={len(cfg.get('qualification_questions') or [])}")
    if CI_MODE:
        report("(b.5) is_auto_generated = true", None, "omitido en CI (confirm skipped)")
    else:
        report("(b.5) is_auto_generated = true", ok_auto,
               f"is_auto_generated={cfg.get('is_auto_generated')}, "
               f"updated_at={cfg.get('bot_config_updated_at')}")

    return cfg


# ── Check (c) — KB documento auto-generado ───────────────────────────────────

def check_c(client: httpx.Client, token: str) -> str | None:
    """Returns the id of the auto-generated KB doc (for cleanup)."""
    auth = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/kb/documents", headers=auth)
    ok = r.status_code == 200
    report("(c.1) GET /kb/documents → 200", ok, f"status={r.status_code}")
    if not ok:
        return None

    docs = r.json()
    auto_docs = [d for d in docs if d.get("is_auto_generated") is True]
    ok_auto = len(auto_docs) >= 1
    if CI_MODE:
        # confirm quedó skipeado — nunca se generó el doc auto-generado.
        report("(c.2) Existe al menos 1 doc con is_auto_generated=true", None,
               "omitido en CI (confirm skipped)")
    else:
        report("(c.2) Existe al menos 1 doc con is_auto_generated=true", ok_auto,
               f"auto_docs={len(auto_docs)}, total={len(docs)}")

    if auto_docs:
        doc = auto_docs[0]
        ok_title   = bool(doc.get("title"))
        ok_preview = doc.get("content_preview") is not None
        report("(c.3) Documento auto-generado tiene título", ok_title,
               f"title={doc.get('title','')[:50]}")
        report("(c.4) Documento auto-generado tiene content_preview", ok_preview,
               f"preview_chars={len(doc.get('content_preview') or '')}")
        return doc["id"]

    return None


# ── Check (d) — Editar config del bot ────────────────────────────────────────

def check_d(client: httpx.Client, token: str, branch_id: str) -> None:
    auth = {"Authorization": f"Bearer {token}"}
    new_prompt = "Bot de prueba Sprint 12 — actualizado manualmente en test."

    r = client.patch(
        f"/api/branches/{branch_id}/bot-config",
        json={"system_prompt": new_prompt, "tone": "formal"},
        headers=auth,
    )
    ok_patch = r.status_code == 200
    report("(d.1) PATCH /branches/{id}/bot-config → 200", ok_patch,
           f"status={r.status_code}")
    if not ok_patch:
        return

    data = r.json()
    ok_updated_at = data.get("bot_config_updated_at") is not None
    ok_prompt     = data.get("system_prompt") == new_prompt
    ok_tone       = data.get("tone") == "formal"
    ok_not_auto   = data.get("is_auto_generated") is False

    report("(d.2) bot_config_updated_at != null tras edición", ok_updated_at,
           f"updated_at={data.get('bot_config_updated_at')}")
    report("(d.3) system_prompt actualizado en response", ok_prompt)
    report("(d.4) tone actualizado a 'formal'", ok_tone, f"tone={data.get('tone')}")
    report("(d.5) is_auto_generated = false tras edición manual", ok_not_auto,
           f"is_auto_generated={data.get('is_auto_generated')}")

    # Verify persistence via GET
    r2 = client.get(f"/api/branches/{branch_id}/bot-config", headers=auth)
    if r2.status_code == 200:
        cfg = r2.json()
        ok_persist = cfg.get("system_prompt") == new_prompt
        report("(d.6) Cambio persiste en GET posterior", ok_persist)
    else:
        report("(d.6) GET para verificar persistencia → 200", False,
               f"status={r2.status_code}")


# ── Check (e) — Regenerar config ─────────────────────────────────────────────

def check_e(client: httpx.Client, token: str, branch_id: str) -> None:
    auth = {"Authorization": f"Bearer {token}"}

    # Capture current generated_at before regeneration
    r_before = client.get(f"/api/branches/{branch_id}/bot-config", headers=auth)
    gen_at_before = r_before.json().get("bot_config_generated_at") if r_before.status_code == 200 else None

    if CI_MODE:
        report("(e.1) POST bot-config/regenerate (omitido en CI — sin ANTHROPIC_API_KEY)", None)
        report("(e.2) Response contiene bot_config", None, "omitido en CI")
        report("(e.3) bot_config_generated_at actualizado", None, "omitido en CI")
        report("(e.4) is_auto_generated reset", None, "omitido en CI")
        return
    print("        ↳ Regenerando config con Claude (puede tardar ~15s)…")
    t0 = time.monotonic()
    r = client.post(f"/api/branches/{branch_id}/bot-config/regenerate", headers=auth)
    elapsed = round(time.monotonic() - t0, 1)

    ok_200 = r.status_code == 200
    report(f"(e.1) POST bot-config/regenerate → 200 ({elapsed}s)", ok_200,
           f"status={r.status_code}")
    if not ok_200:
        report("(e.2) bot_config presente en response", None)
        report("(e.3) bot_config_generated_at actualizado", None)
        return

    data = r.json()
    bc = data.get("bot_config") or {}
    ok_bc = bool(bc.get("system_prompt")) and bool(bc.get("tone")) and isinstance(bc.get("qualification_questions"), list)
    report("(e.2) Response contiene bot_config completo", ok_bc,
           f"keys={list(bc.keys())}")

    # Verify generated_at updated
    r2 = client.get(f"/api/branches/{branch_id}/bot-config", headers=auth)
    if r2.status_code == 200:
        gen_at_after = r2.json().get("bot_config_generated_at")
        ok_updated = gen_at_after is not None and gen_at_after != gen_at_before
        # Note: if content hash is same, KB doc won't be recreated — that's correct
        report("(e.3) bot_config_generated_at se actualizó", ok_updated,
               f"before={gen_at_before}, after={gen_at_after}")
        ok_auto_reset = r2.json().get("is_auto_generated") is True
        report("(e.4) is_auto_generated = true tras regenerar", ok_auto_reset)
    else:
        report("(e.3) GET para verificar generated_at → 200", False)
        report("(e.4) is_auto_generated reset check", None)


# ── Check (f) — CRUD de documentos KB ────────────────────────────────────────

def check_f(client: httpx.Client, token: str) -> None:
    auth = {"Authorization": f"Bearer {token}"}

    # f.1: POST /api/kb/documents
    doc_title   = "Test Sprint 12 — horarios de atención"
    doc_content = (
        "Horarios de atención de la clínica:\n"
        "Lunes a Viernes: 8:00 AM - 7:00 PM\n"
        "Sábados: 9:00 AM - 2:00 PM\n"
        "Domingos: Cerrado\n\n"
        "Para citas urgentes fuera de horario, enviar mensaje por WhatsApp "
        "y el equipo de guardia responderá en máximo 30 minutos."
    )
    print("        ↳ Creando documento KB con embeddings OpenAI…")
    r = client.post("/api/kb/documents",
                    json={"title": doc_title, "content": doc_content},
                    headers=auth)
    ok_create = r.status_code == 201
    report("(f.1) POST /kb/documents → 201", ok_create,
           f"status={r.status_code}" + (f", detail={r.text[:100]}" if not ok_create else ""))
    if not ok_create:
        report("(f.2) doc aparece en GET /kb/documents", None)
        report("(f.3) GET /kb/documents/{id} retorna contenido", None)
        report("(f.4) PATCH /kb/documents/{id} actualiza título", None)
        report("(f.5) DELETE /kb/documents/{id} elimina el doc", None)
        return

    new_doc_id = r.json()["id"]
    _created_doc_ids.append(new_doc_id)

    ok_is_not_auto = r.json().get("is_auto_generated") is False
    report("(f.1b) Nuevo doc tiene is_auto_generated=false", ok_is_not_auto)

    # f.2: GET list — new doc should appear
    r2 = client.get("/api/kb/documents", headers=auth)
    if r2.status_code == 200:
        ids = [d["id"] for d in r2.json()]
        ok_list = new_doc_id in ids
        report("(f.2) Nuevo doc aparece en GET /kb/documents", ok_list,
               f"total_docs={len(ids)}")
    else:
        report("(f.2) GET /kb/documents tras crear → 200", False)

    # f.3: GET detail
    r3 = client.get(f"/api/kb/documents/{new_doc_id}", headers=auth)
    ok_detail = r3.status_code == 200 and bool(r3.json().get("content"))
    report("(f.3) GET /kb/documents/{id} retorna contenido", ok_detail,
           f"content_chars={len(r3.json().get('content') or '') if r3.status_code == 200 else '?'}")

    # f.4: PATCH — update title
    new_title = "Test Sprint 12 — horarios actualizados"
    r4 = client.patch(f"/api/kb/documents/{new_doc_id}",
                      json={"title": new_title},
                      headers=auth)
    ok_patch = r4.status_code == 200 and r4.json().get("title") == new_title
    report("(f.4) PATCH /kb/documents/{id} actualiza título", ok_patch,
           f"new_title={r4.json().get('title') if r4.status_code == 200 else '?'}")

    # f.5: DELETE
    r5 = client.delete(f"/api/kb/documents/{new_doc_id}", headers=auth)
    ok_delete = r5.status_code == 200 and r5.json().get("deleted") is True
    report("(f.5) DELETE /kb/documents/{id} → deleted=true", ok_delete,
           f"response={r5.json() if r5.status_code == 200 else r5.status_code}")

    # Verify doc is gone
    if ok_delete:
        _created_doc_ids.remove(new_doc_id)  # already cleaned
        r6 = client.get(f"/api/kb/documents/{new_doc_id}", headers=auth)
        report("(f.6) Doc eliminado ya no existe (404)", r6.status_code == 404,
               f"status={r6.status_code}")

    # f.7: DELETE auto-generated without ?confirm=true → expect warning
    r7 = client.get("/api/kb/documents", headers=auth)
    if r7.status_code == 200:
        auto_docs = [d for d in r7.json() if d.get("is_auto_generated")]
        if auto_docs:
            r8 = client.delete(f"/api/kb/documents/{auto_docs[0]['id']}", headers=auth)
            ok_warn = r8.status_code == 200 and r8.json().get("deleted") is False and bool(r8.json().get("warning"))
            report("(f.7) DELETE doc auto-generado sin confirm → warning, deleted=false",
                   ok_warn, f"response={r8.json() if r8.status_code == 200 else r8.status_code}")
        else:
            report("(f.7) DELETE auto-generated warning check", None,
                   "No hay docs auto-generados para probar")


# ── Check (g) — Limpieza ─────────────────────────────────────────────────────

def cleanup(client: httpx.Client, token: str, branch_id: str) -> None:
    """Restore the original bot config and delete any docs created during testing."""
    auth = {"Authorization": f"Bearer {token}"}
    cleaned = 0

    # Delete KB docs created during testing (those not already deleted)
    for doc_id in _created_doc_ids:
        r = client.delete(f"/api/kb/documents/{doc_id}?confirm=true", headers=auth)
        if r.status_code == 200:
            cleaned += 1

    # Restore original bot config (system_prompt and tone)
    if _original_bot_config:
        restore_payload: dict = {}
        if _original_bot_config.get("system_prompt"):
            restore_payload["system_prompt"] = _original_bot_config["system_prompt"]
        if _original_bot_config.get("tone"):
            restore_payload["tone"] = _original_bot_config["tone"]
        if _original_bot_config.get("qualification_questions"):
            restore_payload["qualification_questions"] = _original_bot_config["qualification_questions"]
        if restore_payload:
            client.patch(f"/api/branches/{branch_id}/bot-config",
                         json=restore_payload, headers=auth)

    print(f"\n  → Limpieza: {cleaned} doc(s) KB eliminados, config restaurada.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    email, password = get_args()

    print(f"\n{'='*60}")
    print("  Walix Sprint 12 — Bot Config from Onboarding Tests")
    print(f"{'='*60}\n")
    print("  NOTA: Checks a) y e) llaman a Claude (~15s c/u)\n")

    with httpx.Client(base_url=BASE_URL, timeout=60) as client:
        # Login
        token = login(client, email, password)
        if not token:
            print(f"  {_FAIL}  No se pudo hacer login con {email}")
            print(f"  → ¿Está corriendo el backend en {BASE_URL}?\n")
            sys.exit(1)
        print(f"  ✓ Login OK ({email})\n")

        # Get branch ID
        branch_id = get_branch_id(client, token)
        if not branch_id:
            print(f"  {_FAIL}  No se encontraron branches para este tenant\n")
            sys.exit(1)
        print(f"  ✓ Branch: {branch_id[:8]}…\n")

        try:
            # (a) Onboarding flow
            print("── (a) Onboarding analyze + confirm ──")
            check_a(client, token)

            # (b) Persistencia en branch
            print("\n── (b) Persistencia en branch ──")
            check_b(client, token, branch_id)

            # (c) KB documento auto-generado
            print("\n── (c) KB documento auto-generado ──")
            check_c(client, token)

            # (d) Editar config del bot
            print("\n── (d) Editar config del bot ──")
            check_d(client, token, branch_id)

            # (e) Regenerar config
            print("\n── (e) Regenerar config ──")
            check_e(client, token, branch_id)

            # (f) CRUD documentos KB
            print("\n── (f) CRUD documentos KB ──")
            check_f(client, token)

        finally:
            # (g) Limpieza
            print("\n── (g) Limpieza ──")
            cleanup(client, token, branch_id)

    # Summary
    print(f"\n{'='*60}")
    if not failures:
        print("  ✓ TODOS LOS CHECKS PASARON — Sprint 12 bot-config OK\n")
    else:
        print(f"  ✗ FALLOS ({len(failures)}):")
        for f in failures:
            print(f"    - {f}")
        print()
    print(f"{'='*60}\n")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
