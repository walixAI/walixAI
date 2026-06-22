"""test_registration.py — Sprint 9: verifica el flujo completo de auto-registro.

Checks (a–h):
  a) POST /api/v2/auth/register con datos completos → 201 + token
  b) BD: Tenant + Company + Branch + User creados con datos correctos
  c) trial_ends_at == ahora + 14 días (± 60 segundos)
  d) Mismo email → 409
  e) POST /api/auth/check-email email existente → { available: false }
  f) POST /api/auth/check-email email nuevo → { available: true }
  g) PASS/FAIL por check con detalle
  h) Limpieza de datos de prueba

Uso:
  cd backend && .venv/bin/python scripts/test_registration.py
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

BASE_URL = "http://localhost:8000"
_TRIAL_DAYS = 14

_PASS = "✓ PASS"
_FAIL = "✗ FAIL"

failures: list[str] = []
_created_tenant_id: str | None = None


def report(label: str, ok: bool, detail: str = "") -> None:
    tag = _PASS if ok else _FAIL
    if not ok:
        failures.append(label)
    line = f"  {tag}  {label}"
    if detail:
        line += f"\n         {detail}"
    print(line)


def unique_email() -> str:
    return f"test_reg_{uuid.uuid4().hex[:8]}@walix-test.mx"


# ─────────────────────────────────────────────────────────────────────────────
# a) Registro completo → 201 + token
# ─────────────────────────────────────────────────────────────────────────────

async def check_a(client: httpx.AsyncClient, email: str) -> str | None:
    """Returns access_token if successful, None on failure."""
    print("a) POST /api/v2/auth/register ────────────────────────────")
    payload = {
        "name": "Test Owner",
        "email": email,
        "password": "walix2026",
        "workspace_name": "Clínica Test Sprint 9",
        "phone": "+52 55 0000 0000",
        "referral_source": "google",
    }
    resp = client.post("/api/v2/auth/register", json=payload)
    ok = resp.status_code == 201
    report("POST /api/v2/auth/register → 201", ok, f"status={resp.status_code} body={resp.text[:200]}")
    if not ok:
        return None

    data = resp.json()
    has_token = bool(data.get("access_token"))
    has_user  = bool(data.get("user", {}).get("id"))
    report("Respuesta incluye access_token y user.id", has_token and has_user)
    return data.get("access_token")


# ─────────────────────────────────────────────────────────────────────────────
# b) Verificar Tenant + Company + Branch + User en BD
# ─────────────────────────────────────────────────────────────────────────────

async def check_b(email: str) -> str | None:
    """Returns tenant_id if found, None on failure."""
    global _created_tenant_id
    print("\nb) Verificar entidades en BD ────────────────────────────")
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Tenant, Company, Branch
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        report("User creado en BD", user is not None, f"email={email}")
        if user is None:
            return None

        tenant = await db.get(Tenant, user.tenant_id)
        report("Tenant creado", tenant is not None)
        if tenant is None:
            return None

        plan_val = getattr(tenant.plan, "value", str(tenant.plan))
        report("Tenant.plan == 'trial'", plan_val == "trial", f"plan={plan_val}")
        report(
            "Tenant.name == workspace_name",
            tenant.name == "Clínica Test Sprint 9",
            f"name={tenant.name}",
        )

        company = (await db.execute(
            select(Company).where(Company.tenant_id == tenant.id)
        )).scalar_one_or_none()
        report("Company creada", company is not None)

        branch = (await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id)
        )).scalar_one_or_none()
        report("Branch creada", branch is not None)
        if branch:
            report(
                "Branch.name contiene workspace_name",
                "Clínica Test Sprint 9" in branch.name,
                f"branch.name={branch.name}",
            )

        report("User.branch_id == None (owner accede a todas)", user.branch_id is None)
        report("User.role == 'owner'", getattr(user.role, "value", str(user.role)) == "owner")

        _created_tenant_id = str(tenant.id)
        return _created_tenant_id


# ─────────────────────────────────────────────────────────────────────────────
# c) trial_ends_at == now + 14 días (± 60 s)
# ─────────────────────────────────────────────────────────────────────────────

async def check_c(tenant_id: str) -> None:
    print("\nc) trial_ends_at = now + 14 días ───────────────────────")
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Tenant
    from uuid import UUID

    async with AsyncSessionLocal() as db:
        tenant = await db.get(Tenant, UUID(tenant_id))

    if tenant is None or tenant.trial_ends_at is None:
        report("trial_ends_at está seteado", False)
        return

    ends = tenant.trial_ends_at
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)

    expected = datetime.now(timezone.utc) + timedelta(days=_TRIAL_DAYS)
    diff_seconds = abs((ends - expected).total_seconds())
    report(
        f"trial_ends_at ≈ now + {_TRIAL_DAYS} días (± 60 s)",
        diff_seconds <= 60,
        f"trial_ends_at={ends.isoformat()} diff={diff_seconds:.1f}s",
    )


# ─────────────────────────────────────────────────────────────────────────────
# d) Mismo email → 409
# ─────────────────────────────────────────────────────────────────────────────

async def check_d(client: httpx.AsyncClient, email: str) -> None:
    print("\nd) Registrar mismo email → 409 ─────────────────────────")
    resp = client.post("/api/v2/auth/register", json={
        "name": "Otro", "email": email, "password": "walix2026",
        "workspace_name": "Duplicado",
    })
    report("Registro duplicado → 409 Conflict", resp.status_code == 409,
           f"status={resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# e-f) check-email endpoint
# ─────────────────────────────────────────────────────────────────────────────

async def check_ef(client: httpx.AsyncClient, existing_email: str) -> None:
    print("\ne) POST /api/auth/check-email (email existente) ─────────")
    resp = client.post("/api/auth/check-email", json={"email": existing_email})
    data = resp.json() if resp.status_code == 200 else {}
    report("check-email email existente → { available: false }",
           resp.status_code == 200 and data.get("available") is False,
           f"status={resp.status_code} body={data}")

    print("\nf) POST /api/auth/check-email (email nuevo) ─────────────")
    new_email = unique_email()
    resp2 = client.post("/api/auth/check-email", json={"email": new_email})
    data2 = resp2.json() if resp2.status_code == 200 else {}
    report("check-email email nuevo → { available: true }",
           resp2.status_code == 200 and data2.get("available") is True,
           f"status={resp2.status_code} body={data2}")


# ─────────────────────────────────────────────────────────────────────────────
# h) Limpiar datos de prueba
# ─────────────────────────────────────────────────────────────────────────────

async def cleanup(email: str) -> None:
    print("\nh) Limpiando datos de prueba ────────────────────────────")
    from sqlalchemy import select, delete
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Tenant, Company, Branch
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print("  (nada que limpiar)")
            return

        tenant_id = user.tenant_id
        await db.execute(delete(User).where(User.tenant_id == tenant_id))
        await db.execute(delete(Branch).where(Branch.tenant_id == tenant_id))

        companies = (await db.execute(
            select(Company).where(Company.tenant_id == tenant_id)
        )).scalars().all()
        for c in companies:
            await db.execute(delete(Branch).where(Branch.company_id == c.id))
        await db.execute(delete(Company).where(Company.tenant_id == tenant_id))
        await db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await db.commit()

    print("  Tenant + Company + Branch + User eliminados")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> int:
    print(f"\n{'═' * 58}")
    print("  WALIX — Verificación Sprint 9: Auto-registro")
    print(f"{'═' * 58}\n")

    email = unique_email()
    token: str | None = None
    tenant_id: str | None = None

    with httpx.Client(base_url=BASE_URL, timeout=15) as client:
        token = await check_a(client, email)
        if token:
            tenant_id = await check_b(email)
            if tenant_id:
                await check_c(tenant_id)
            await check_d(client, email)
            await check_ef(client, email)
        else:
            print("  ⚠ Registro falló — omitiendo checks b-f")
            print("  Verifica que el servidor esté corriendo: uvicorn app.main:app --port 8000")

    await cleanup(email)

    print(f"\n{'─' * 58}")
    if not failures:
        print(f"  {_PASS}  Todos los checks pasaron.\n")
    else:
        print(f"  {_FAIL}  {len(failures)} check(s) fallaron:")
        for f in failures:
            print(f"    • {f}")
        print()

    return len(failures)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
