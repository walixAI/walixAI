"""purge_utel_demo_data.py — Borra los datos sembrados por seed_utel_demo_a.py.

El manifiesto (.utel_demo_manifest.json, escrito por seed_utel_demo_a.py) es
la ÚNICA fuente de verdad — si no existe, este script aborta. No intenta
borrar por heurística basada solo en el tag (alguien pudo haber editado el
tag manualmente después de sembrar la demo).

Modo auditoría (default): lee el manifiesto, cuenta cuántas filas de cada
tipo existen todavía en BD, imprime el resumen y sale SIN borrar nada.

Modo ejecución (--confirm): borra en orden correcto (children primero:
messages -> conversations -> activities -> lead_tags -> leads -> tag ->
los 4 usuarios demo), todo en una transacción.

Uso:
    .venv/Scripts/python.exe scripts/admin/purge_utel_demo_data.py             (auditoría)
    .venv/Scripts/python.exe scripts/admin/purge_utel_demo_data.py --confirm   (borra)
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models.activity import LeadActivity
from app.models.conversation import Conversation, Message
from app.models.lead import Lead
from app.models.tag import Tag, lead_tags_table
from app.models.user import User

MANIFEST_PATH = Path(__file__).resolve().parent / ".utel_demo_manifest.json"


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(f"No existe el manifiesto ({MANIFEST_PATH}) — abortando.")
        print("No se intenta borrar por heurística basada solo en el tag.")
        sys.exit(1)
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


async def _count_existing(db, model, ids: list[str]) -> int:
    if not ids:
        return 0
    uuids = [uuid.UUID(i) for i in ids]
    rows = (await db.execute(select(model.id).where(model.id.in_(uuids)))).scalars().all()
    return len(rows)


async def _audit_mode(manifest: dict) -> int:
    print("=" * 70)
    print("  purge_utel_demo_data.py — AUDITORÍA (ningún cambio aplicado)")
    print("=" * 70)
    print()
    rows = (
        ("Usuarios demo", "user_ids", User),
        ("Leads", "lead_ids", Lead),
        ("Conversations", "conversation_ids", Conversation),
        ("Messages", "message_ids", Message),
        ("LeadActivity", "activity_ids", LeadActivity),
    )
    async with AsyncSessionLocal() as db:
        counts = {
            key: await _count_existing(db, model, manifest.get(key, []))
            for _, key, model in rows
        }
        tag_ids = [manifest["tag_id"]] if manifest.get("tag_id") else []
        tag_count = await _count_existing(db, Tag, tag_ids)

    print(f"Manifiesto: {MANIFEST_PATH} (creado {manifest.get('created_at', 'N/A')})")
    print()
    print("Filas que todavía existen en BD (de las que sembró el manifiesto):")
    for label, key, _model in rows:
        total = len(manifest.get(key, []))
        print(f"  {label:<16} {counts[key]}/{total} existen todavía")
    print(f"  {'Tag':<16} {tag_count}/1 existe todavía")
    print()
    print("Para borrar de verdad: python scripts/admin/purge_utel_demo_data.py --confirm")
    return 0


async def _execute_mode(manifest: dict) -> int:
    print("=" * 70)
    print("  purge_utel_demo_data.py — MODO EJECUCIÓN (--confirm)")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        message_ids = [uuid.UUID(i) for i in manifest.get("message_ids", [])]
        conversation_ids = [uuid.UUID(i) for i in manifest.get("conversation_ids", [])]
        activity_ids = [uuid.UUID(i) for i in manifest.get("activity_ids", [])]
        lead_ids = [uuid.UUID(i) for i in manifest.get("lead_ids", [])]
        user_ids = [uuid.UUID(i) for i in manifest.get("user_ids", [])]
        tag_id = uuid.UUID(manifest["tag_id"]) if manifest.get("tag_id") else None

        deleted_messages = 0
        if message_ids:
            deleted_messages = (await db.execute(
                delete(Message).where(Message.id.in_(message_ids))
            )).rowcount

        deleted_conversations = 0
        if conversation_ids:
            deleted_conversations = (await db.execute(
                delete(Conversation).where(Conversation.id.in_(conversation_ids))
            )).rowcount

        deleted_activities = 0
        if activity_ids:
            deleted_activities = (await db.execute(
                delete(LeadActivity).where(LeadActivity.id.in_(activity_ids))
            )).rowcount

        deleted_lead_tags = 0
        if lead_ids and tag_id:
            deleted_lead_tags = (await db.execute(
                delete(lead_tags_table).where(
                    lead_tags_table.c.lead_id.in_(lead_ids),
                    lead_tags_table.c.tag_id == tag_id,
                )
            )).rowcount

        deleted_leads = 0
        if lead_ids:
            deleted_leads = (await db.execute(
                delete(Lead).where(Lead.id.in_(lead_ids))
            )).rowcount

        deleted_tag = 0
        if tag_id:
            deleted_tag = (await db.execute(
                delete(Tag).where(Tag.id == tag_id)
            )).rowcount

        deleted_users = 0
        if user_ids:
            deleted_users = (await db.execute(
                delete(User).where(User.id.in_(user_ids))
            )).rowcount

        await db.commit()

    print("✓ Purga aplicada.")
    print(f"  messages       borrados: {deleted_messages}")
    print(f"  conversations  borradas: {deleted_conversations}")
    print(f"  activities     borradas: {deleted_activities}")
    print(f"  lead_tags      borrados: {deleted_lead_tags}")
    print(f"  leads          borrados: {deleted_leads}")
    print(f"  tag            borrado:  {deleted_tag}")
    print(f"  usuarios demo  borrados: {deleted_users}")
    print()
    print(f"  Manifiesto conservado en {MANIFEST_PATH} (podés borrarlo manualmente si querés).")
    return 0


async def main() -> int:
    confirm = "--confirm" in sys.argv[1:]
    manifest = _load_manifest()
    if confirm:
        return await _execute_mode(manifest)
    return await _audit_mode(manifest)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
