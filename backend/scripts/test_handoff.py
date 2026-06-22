"""Sprint 3 T-25 — test_handoff.py

Verifica el flujo completo de handoff contra el backend local:
  handoff → reply → listar agentes → asignar → return-to-bot

Usa `asistente@clinica.com` (asesor de Monterrey).  Si la sucursal no tiene
leads crea uno mínimo en la BD directamente para que el test sea autónomo.

Nota: /reply requiere credenciales de WhatsApp configuradas en la sucursal.
      En local el test usa /messages (envío interno) para no depender de WA.

Corre desde backend/:
    .venv/bin/python scripts/test_handoff.py
"""
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

import httpx
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation, ConversationHandler, ConversationStatus
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.tenant import Branch

BASE_URL = "http://localhost:8000"
ASISTENTE_EMAIL = "asistente@clinica.com"
PASSWORD = "walix2026"

_ok = 0
_fail = 0


def ok(label: str) -> None:
    global _ok
    _ok += 1
    print(f"  ✓ {label}")


def fail(label: str, detail: str = "") -> None:
    global _fail
    _fail += 1
    suffix = f" — {detail}" if detail else ""
    print(f"  ✗ {label}{suffix}")


def check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        ok(label)
    else:
        fail(label, detail)
    return condition


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _ensure_lead(branch_id: uuid.UUID) -> uuid.UUID:
    """Returns a lead ID in bot mode with an active conversation.

    Uses the most recent existing lead if one has a valid conversation;
    otherwise creates a minimal test lead directly in the DB.
    """
    async with AsyncSessionLocal() as db:
        # Try to reuse the most recent lead that already has a conversation
        result = await db.execute(
            select(Lead)
            .where(Lead.branch_id == branch_id)
            .order_by(Lead.created_at.desc())
        )
        for lead in result.scalars().all():
            conv_result = await db.execute(
                select(Conversation).where(
                    Conversation.lead_id == lead.id,
                    Conversation.status != ConversationStatus.CLOSED,
                )
            )
            conv = conv_result.scalar_one_or_none()
            if conv:
                # Reset to bot so each test run starts clean
                conv.current_handler = ConversationHandler.BOT
                conv.handler_user_id = None
                conv.status = ConversationStatus.ACTIVE
                await db.commit()
                print(f"  → Reutilizando lead: {lead.id} (reseteado a bot)")
                return lead.id

        # No usable lead found — create a minimal one
        branch = await db.get(Branch, branch_id)
        if branch is None:
            raise RuntimeError(f"Branch {branch_id} no encontrado en la BD")

        lead = Lead(
            branch_id=branch.id,
            tenant_id=branch.tenant_id,
            wa_phone=f"521550{uuid.uuid4().hex[:7]}",
            name="Lead de prueba T-25",
            source=LeadSource.WHATSAPP,
            status=LeadStatus.EN_CALIFICACION,
            qualification_data={},
        )
        db.add(lead)
        await db.flush()

        conv = Conversation(
            lead_id=lead.id,
            branch_id=branch.id,
            status=ConversationStatus.ACTIVE,
            current_handler=ConversationHandler.BOT,
        )
        db.add(conv)
        await db.commit()
        print(f"  → Lead de prueba creado: {lead.id}")
        return lead.id


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 62)
    print("Sprint 3 T-25 — test_handoff.py")
    print("=" * 62)

    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:

        # ── a. Login ──────────────────────────────────────────────────────────
        print(f"\n[a] Login — {ASISTENTE_EMAIL}")
        r = client.post("/api/auth/login", json={"email": ASISTENTE_EMAIL, "password": PASSWORD})
        if not check("POST /auth/login 200", r.status_code == 200, f"HTTP {r.status_code}"):
            print("  No se puede continuar sin token.")
            return

        data = r.json()
        token: str = data["access_token"]
        user = data["user"]
        branch_id_str: str | None = user.get("branch_id")
        auth = {"Authorization": f"Bearer {token}"}

        if not check("branch_id presente en user", branch_id_str is not None,
                     "usa asistente@clinica.com, no owner"):
            return

        branch_id = uuid.UUID(branch_id_str)

        # ── Preparar lead de prueba ───────────────────────────────────────────
        print("\n  Preparando lead de prueba...")
        try:
            lead_id = asyncio.run(_ensure_lead(branch_id))
        except Exception as exc:
            fail("Preparar lead", str(exc))
            return

        # ── c. Handoff ────────────────────────────────────────────────────────
        print(f"\n[c] Handoff — lead {lead_id}")
        r = client.post(f"/api/leads/{lead_id}/handoff", headers=auth)
        check("POST /handoff 200", r.status_code == 200,
              f"HTTP {r.status_code}: {r.text[:100]}")

        # ── d. Verificar handler = human ──────────────────────────────────────
        print("\n[d] Verificar current_handler = human")
        r = client.get(f"/api/leads/{lead_id}/conversation", headers=auth)
        check("GET /conversation 200", r.status_code == 200, r.text[:80])
        if r.status_code == 200:
            conv = r.json()
            check("current_handler == 'human'",
                  conv["current_handler"] == "human",
                  f"got: {conv['current_handler']}")

        # ── e. Mensaje humano (via /messages para no depender de WA creds) ───
        MSG = "Hola, soy Ana de la clínica ¿cómo estás?"
        print("\n[e] Enviar mensaje como humano (POST /messages)")
        r = client.post(f"/api/leads/{lead_id}/messages",
                        json={"text": MSG}, headers=auth)
        check("POST /messages 200", r.status_code == 200,
              f"HTTP {r.status_code}: {r.text[:100]}")

        # ── f. Verificar mensaje en conversación ──────────────────────────────
        print("\n[f] Verificar mensaje con sent_by_user_id != null")
        r = client.get(f"/api/leads/{lead_id}/conversation", headers=auth)
        if r.status_code == 200:
            msgs = r.json()["messages"]
            human_msgs = [m for m in msgs if m.get("sent_by_user_id") is not None]
            check("Al menos un mensaje tiene sent_by_user_id != null",
                  len(human_msgs) > 0,
                  f"total msgs={len(msgs)}, con user_id={len(human_msgs)}")
            if human_msgs:
                check("Contenido del último mensaje correcto",
                      human_msgs[-1]["content"] == MSG,
                      f"got: {human_msgs[-1]['content'][:60]}")

        # ── g. Listar agentes ─────────────────────────────────────────────────
        print(f"\n[g] GET /branches/{branch_id_str[:8]}…/agents")
        r = client.get(f"/api/branches/{branch_id}/agents", headers=auth)
        agents: list[dict] = []
        check("GET /agents 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            agents = r.json()
            check(f"Al menos un agente ({len(agents)})", len(agents) > 0,
                  "sin agentes — corre add_test_users.py")
            doctors = [a for a in agents if a["role"] == "doctor"]
            check(f"Hay doctor(es) en el branch ({len(doctors)})", len(doctors) > 0,
                  "sin doctores — corre add_test_users.py")
            for a in agents[:3]:
                print(f"     {a['name']:<22} role={a['role']:<8} active_leads={a['active_leads']}")

        # ── h. Asignar al primer agente ───────────────────────────────────────
        print("\n[h] Asignar lead al primer agente de la lista")
        assigned_ok = False
        if agents:
            first = agents[0]
            r = client.post(f"/api/leads/{lead_id}/assign",
                            json={"user_id": first["id"]}, headers=auth)
            assigned_ok = check(
                f"POST /assign → {first['name']} ({first['role']})",
                r.status_code == 200,
                f"HTTP {r.status_code}: {r.text[:100]}",
            )
        else:
            fail("Asignar lead", "sin agentes disponibles")

        # ── i. Verificar assigned_to ──────────────────────────────────────────
        print("\n[i] Verificar lead.assigned_to actualizado")
        if assigned_ok:
            r = client.get(f"/api/leads/{lead_id}", headers=auth)
            if r.status_code == 200:
                detail = r.json()
                check("lead.assigned_to == agente.id",
                      detail.get("assigned_to") == first["id"],
                      f"got: {detail.get('assigned_to')}")
                check("lead.assigned_to_name correcto",
                      detail.get("assigned_to_name") == first["name"],
                      f"got: {detail.get('assigned_to_name')}")

        # ── j. Return to bot ──────────────────────────────────────────────────
        print("\n[j] Return to bot")
        r = client.post(f"/api/leads/{lead_id}/return-to-bot", headers=auth)
        check("POST /return-to-bot 200", r.status_code == 200,
              f"HTTP {r.status_code}: {r.text[:100]}")

        # ── k. Verificar handler = bot ────────────────────────────────────────
        print("\n[k] Verificar current_handler = bot")
        r = client.get(f"/api/leads/{lead_id}/conversation", headers=auth)
        if r.status_code == 200:
            conv = r.json()
            check("current_handler == 'bot'",
                  conv["current_handler"] == "bot",
                  f"got: {conv['current_handler']}")

    # ── Resumen ───────────────────────────────────────────────────────────────
    total = _ok + _fail
    print()
    print("=" * 62)
    print(f"Resultado: {_ok}/{total} checks pasaron")
    if _fail:
        print(f"  {_fail} fallo(s) — revisa los ✗ arriba.")
    else:
        print("  Todos los checks pasaron.")
    print("=" * 62)


if __name__ == "__main__":
    main()
    sys.exit(1 if _fail else 0)
