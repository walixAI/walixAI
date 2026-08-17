"""seed_demo_deals.py — Crea datos demo de Deals para un tenant.

NUNCA toca la clínica beta. Verifica el tenant objetivo contra
CLINICA_TENANT_ID y aborta si coinciden.

Uso:
    cd backend
    export CLINICA_TENANT_ID=72b10c98-8b9d-4d03-9e17-085a8a77a98f
    .venv/bin/python scripts/seed_demo_deals.py --tenant-id 7e4ec8d0-...

Argumentos opcionales:
    --tenant-id   UUID del tenant demo (o env DEMO_TENANT_ID)
    --email       Email del usuario owner/admin del tenant (o env DEMO_EMAIL)
    --password    Contraseña (o env DEMO_PWD)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import text

from app.core.database import AsyncSessionLocal

# ── Guardia anti-clínica beta ─────────────────────────────────────────────────
_DEFAULT_CLINICA_ID = "72b10c98-8b9d-4d03-9e17-085a8a77a98f"
CLINICA_TENANT_ID   = os.environ.get("CLINICA_TENANT_ID", _DEFAULT_CLINICA_ID)

BASE = "http://localhost:8000/api"

DEMO_LEADS = [
    ("Lucía",    "Fernández",  "+5215500001001"),
    ("Omar",     "Castillo",   "+5215500001002"),
    ("Isabel",   "Reyes",      "+5215500001003"),
    ("Gustavo",  "Morales",    "+5215500001004"),
    ("Valeria",  "Soto",       "+5215500001005"),
]

# (title, amount, probability, stage_index, is_won, is_lost, days_ago_won)
# stage_index: posición relativa entre las etapas abiertas (0-based)
DEMO_DEALS = [
    ("[DEMO] Consulta inicial básica",        4_500, 20, 0, False, False, 0),
    ("[DEMO] Evaluación diagnóstica",         6_200, 30, 0, False, False, 0),
    ("[DEMO] Primer contacto calificado",     8_000, 40, 1, False, False, 0),
    ("[DEMO] Propuesta enviada",             12_000, 55, 1, False, False, 0),
    ("[DEMO] Cita confirmada — paciente A",  15_000, 65, 2, False, False, 0),
    ("[DEMO] Cita confirmada — paciente B",  18_500, 70, 2, False, False, 0),
    ("[DEMO] En tratamiento — protocolo GH", 48_000, 80, 3, False, False, 0),
    ("[DEMO] Alta médica — caso exitoso",    52_000, 100, 0, True,  False, 5),
    ("[DEMO] Cierre acelerado — remisión",   35_000, 100, 0, True,  False, 12),
    ("[DEMO] Cierre mes pasado — follow-up", 28_000, 100, 0, True,  False, 22),
    ("[DEMO] No regresó — sin seguimiento",      0,   0, 0, False, True,  0),
    ("[DEMO] Precio fuera de alcance",           0,   0, 0, False, True,  0),
]


async def main(tenant_id: str, email: str, password: str) -> None:
    # ── Guardia ───────────────────────────────────────────────────────────────
    if tenant_id.lower() == CLINICA_TENANT_ID.lower():
        print(f"❌ ABORTANDO: el tenant objetivo ({tenant_id}) ES la clínica beta.")
        print(f"   Nunca sembramos datos demo en producción.")
        print(f"   Usa un tenant de prueba distinto o ajusta CLINICA_TENANT_ID.")
        sys.exit(1)

    async with httpx.AsyncClient(timeout=30) as c:
        # Login
        r = await c.post(f"{BASE}/auth/login", json={"email": email, "password": password})
        if r.status_code != 200:
            print(f"❌ Login falló: {r.status_code} {r.text[:120]}")
            sys.exit(1)
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        print(f"✓ Login como {email}")

        # Verificar que el usuario pertenece al tenant objetivo
        me = (await c.get(f"{BASE}/auth/me", headers=h)).json()
        user_tenant = me["user"]["tenant_id"]
        if user_tenant != tenant_id:
            print(f"❌ El usuario pertenece al tenant {user_tenant}, no {tenant_id}")
            sys.exit(1)

        # ── Idempotencia: verificar si ya hay deals demo ──────────────────────
        existing = (await c.get(f"{BASE}/deals?limit=1", headers=h)).json()
        demo_count = sum(
            1 for d in existing.get("items", [])
            if d.get("title", "").startswith("[DEMO]")
        )
        # También buscar en todas las páginas
        if existing.get("total", 0) > 0:
            all_deals = (await c.get(f"{BASE}/deals?limit=100", headers=h)).json()
            demo_count = sum(
                1 for d in all_deals.get("items", [])
                if d.get("title", "").startswith("[DEMO]")
            )
            if demo_count > 0:
                print(f"⚠  Ya existen {demo_count} deals [DEMO] — omitiendo seed (idempotente).")
                return

        # ── Resolver branch_id (owners multi-branch tienen branch_id=None) ────
        me_info = (await c.get(f"{BASE}/auth/me", headers=h)).json()
        branch_id = me_info["user"].get("branch_id")
        if not branch_id:
            branches = (await c.get(f"{BASE}/branches", headers=h)).json()
            if not branches:
                print("❌ No hay branches en este tenant.")
                sys.exit(1)
            branch_id = branches[0]["id"]

        # ── Pipeline stages del tenant ────────────────────────────────────────
        board = (await c.get(f"{BASE}/pipeline/board?branch_id={branch_id}", headers=h)).json()
        stages = sorted(board.get("stages", []), key=lambda s: s["order_index"])
        open_stages = [s for s in stages if not s["is_won"] and not s["is_lost"]]
        won_stage   = next((s for s in stages if s["is_won"]),  None)
        lost_stage  = next((s for s in stages if s["is_lost"]), None)

        if not open_stages:
            print("❌ El tenant no tiene etapas de pipeline configuradas.")
            sys.exit(1)

        print(f"✓ {len(stages)} etapas encontradas")

        # ── Crear leads demo (directo en DB para soportar owner sin branch_id) ─
        print(f"\n── Creando {len(DEMO_LEADS)} leads demo ─────────────────────")
        lead_ids: list[str] = []
        async with AsyncSessionLocal() as db:
            for name, last_name, phone in DEMO_LEADS:
                # Verificar si ya existe por teléfono
                existing = (await db.execute(
                    text("SELECT id FROM leads WHERE wa_phone = :p AND tenant_id = :t AND deleted_at IS NULL"),
                    {"p": phone, "t": uuid.UUID(tenant_id)},
                )).fetchone()
                if existing:
                    lead_ids.append(str(existing[0]))
                    print(f"  ~ [DEMO] {name} {last_name} (ya existe)")
                    continue

                lead_id = uuid.uuid4()
                await db.execute(
                    text("""
                        INSERT INTO leads (id, tenant_id, branch_id, wa_phone, name, last_name,
                                          prospection_source, status, sentiment, source,
                                          qualification_data, created_at, updated_at)
                        VALUES (:id, :tenant_id, :branch_id, :phone, :name, :last_name,
                                'manual', 'nuevo', 'neutral', 'manual',
                                '{}', NOW(), NOW())
                    """),
                    {
                        "id":        lead_id,
                        "tenant_id": uuid.UUID(tenant_id),
                        "branch_id": uuid.UUID(branch_id),
                        "phone":     phone,
                        "name":      f"[DEMO] {name}",
                        "last_name": last_name,
                    },
                )
                lead_ids.append(str(lead_id))
                print(f"  + [DEMO] {name} {last_name}")
            await db.commit()

        if not lead_ids:
            print("❌ No se pudo crear ningún lead demo.")
            sys.exit(1)
        print(f"✓ {len(lead_ids)} leads disponibles")

        # ── Crear deals demo ──────────────────────────────────────────────────
        print(f"\n── Creando {len(DEMO_DEALS)} deals demo ─────────────────────")
        created_deals: list[tuple[str, bool, int]] = []  # (id, is_won, days_ago)
        lead_cursor = 0

        for title, amount, prob, stage_idx, is_won, is_lost, days_ago in DEMO_DEALS:
            # Resolver etapa
            if is_won and won_stage:
                stage_id = won_stage["id"]
            elif is_lost and lost_stage:
                stage_id = lost_stage["id"]
            else:
                idx = min(stage_idx, len(open_stages) - 1)
                stage_id = open_stages[idx]["id"]

            lead_id = lead_ids[lead_cursor % len(lead_ids)]
            lead_cursor += 1

            payload: dict = {
                "lead_id":           lead_id,
                "pipeline_stage_id": stage_id,
                "title":             title,
                "amount":            str(amount),
                "probability":       prob,
            }
            r = await c.post(f"{BASE}/deals", headers=h, json=payload)
            if r.status_code not in (200, 201):
                print(f"  ✗ {title[:50]}: {r.status_code} {r.text[:80]}")
                continue

            deal_id = r.json()["id"]

            # Marcar won/lost vía PATCH
            if is_won or is_lost:
                await c.patch(f"{BASE}/deals/{deal_id}", headers=h,
                              json={"is_won": is_won, "is_lost": is_lost})

            created_deals.append((deal_id, is_won, days_ago))
            flag = " (won)" if is_won else " (lost)" if is_lost else ""
            print(f"  + {title[:55]}{flag}")

        # ── Retrodetar updated_at para los won (timeline demo) ────────────────
        won_backdated = [(did, d) for did, w, d in created_deals if w and d > 0]
        if won_backdated:
            print("\n── Backdatando updated_at para el timeline ──────────────")
            now_utc = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                for deal_id, days_ago in won_backdated:
                    past = now_utc - timedelta(days=days_ago)
                    await db.execute(
                        text("UPDATE deals SET updated_at = :ts WHERE id = :id"),
                        {"ts": past, "id": uuid.UUID(deal_id)},
                    )
                    print(f"  ← {deal_id[:8]}…  updated_at = -{days_ago}d")
                await db.commit()

        # ── Resumen ───────────────────────────────────────────────────────────
        print("\n── Resumen ──────────────────────────────────────────────────")
        kpis = (await c.get(f"{BASE}/dashboard/kpis", headers=h)).json()
        print(f"  pipelineValue : ${kpis.get('pipelineValue', 0):,} MXN")
        print(f"  activeDeals   : {kpis.get('activeDeals', 0)}")
        print(f"  closeRate     : {kpis.get('closeRate', 0)}%")
        print("\n✅ Seed demo completado")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", default=os.environ.get("DEMO_TENANT_ID"))
    parser.add_argument("--email",     default=os.environ.get("DEMO_EMAIL", "test4@mail.com"))
    parser.add_argument("--password",  default=os.environ.get("DEMO_PWD", "walix2026"))
    args = parser.parse_args()

    if not args.tenant_id:
        print("❌ Se requiere --tenant-id o DEMO_TENANT_ID")
        sys.exit(1)

    asyncio.run(main(args.tenant_id, args.email, args.password))
