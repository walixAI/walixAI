"""test_nomenclatura.py — verifica nomenclatura dinámica (Industry Templates) en BD."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.tenant import Tenant


async def main() -> None:
    print("Verificando nomenclatura dinámica en BD...\n")
    ok_count = 0
    fail_count = 0

    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(select(Tenant))).scalars().all()

        if not tenants:
            print("No hay tenants en la BD.")
            return

        for t in tenants:
            # contact_statuses_config es JSONB — ya es lista nativa, no string
            statuses: list = t.contact_statuses_config or []
            status_labels = [s.get("label", s.get("key", "?")) for s in statuses if isinstance(s, dict)]

            print(f"Tenant: {t.name}")
            print(f"  industry_key:     {t.industry_key}")
            print(f"  entity_name:      {t.entity_name}")
            print(f"  entity_plural:    {t.entity_plural}")
            print(f"  contact_statuses: {status_labels}")

            configured = bool(t.entity_name and t.entity_plural and len(statuses) > 0)
            if configured:
                print(f"  ✓ OK\n")
                ok_count += 1
            else:
                missing = []
                if not t.entity_name:
                    missing.append("entity_name")
                if not t.entity_plural:
                    missing.append("entity_plural")
                if not statuses:
                    missing.append("contact_statuses")
                print(f"  ✗ FALTA: {', '.join(missing)}\n")
                fail_count += 1

    print(f"Resultado: {ok_count} OK  |  {fail_count} sin configurar")
    if ok_count == 0 and fail_count > 0:
        sys.exit(1)


asyncio.run(main())
