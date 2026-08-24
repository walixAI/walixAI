"""test_impersonation.py — Verificación end-to-end del hallazgo #9
(docs/PERMISSIONS_DRIFT_BACKLOG.md): impersonación de platform_owner.

Corre contra la base de datos REAL configurada en .env (settings.
effective_database_url, hoy el rol admin — ver app/core/config.py), vía la
app ASGI en proceso (httpx.AsyncClient + ASGITransport), así que ejercita
la pila de middleware completa (ImpersonationReadOnlyMiddleware,
TenantContextMiddleware, TrialGuardMiddleware) tal como corre en
producción, sin necesitar un servidor uvicorn corriendo aparte.

Crea dos tenants desechables propios (no usa el tenant clínica beta —
más simple aislar en tenants nuevos que resetear datos compartidos) y los
borra al final, éxito o no.

Verificaciones:
  c) Con token de impersonación, GET /api/leads devuelve SOLO leads del
     tenant OBJETIVO (nunca el lead del tenant "home" del platform_owner).
  d) Con el mismo token, POST /api/goals/monthly-goals devuelve 403 con
     el detail esperado, y NO crea ninguna MonthlyGoal.
  e) Con un token normal (sin read_only_impersonation), el mismo POST
     sigue funcionando (200, meta creada) — prueba de que el middleware
     no rompe el flujo normal.

Uso:
    .venv/Scripts/python.exe scripts/diagnostics/test_impersonation.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.goals import MonthlyGoal
from app.models.lead import Lead
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole


async def _setup() -> dict:
    async with AsyncSessionLocal() as db:
        tag = uuid.uuid4().hex[:8]

        home_tenant = Tenant(
            name=f"[test_impersonation] Home {tag}",
            email=f"po-home-{tag}@walix.test",
            plan=TenantPlan.STARTER,
            is_active=True,
        )
        db.add(home_tenant)
        await db.flush()
        home_company = Company(tenant_id=home_tenant.id, name="Home Co")
        db.add(home_company)
        await db.flush()
        home_branch = Branch(company_id=home_company.id, tenant_id=home_tenant.id, name="Home Branch", is_active=True)
        db.add(home_branch)
        await db.flush()

        platform_owner = User(
            tenant_id=home_tenant.id,
            branch_id=home_branch.id,
            email=f"po-{tag}@walix.test",
            name="Platform Owner (test_impersonation)",
            hashed_password="not-used-token-built-directly",
            role=UserRole.PLATFORM_OWNER,
            is_active=True,
        )
        db.add(platform_owner)
        await db.flush()

        home_lead = Lead(
            branch_id=home_branch.id,
            tenant_id=home_tenant.id,
            wa_phone="+520000000001",
            name="Lead de HOME — NO debe verse durante impersonación",
        )
        db.add(home_lead)

        target_tenant = Tenant(
            name=f"[test_impersonation] Target {tag}",
            email=f"target-{tag}@walix.test",
            plan=TenantPlan.STARTER,
            is_active=True,
        )
        db.add(target_tenant)
        await db.flush()
        target_company = Company(tenant_id=target_tenant.id, name="Target Co")
        db.add(target_company)
        await db.flush()
        target_branch = Branch(company_id=target_company.id, tenant_id=target_tenant.id, name="Target Branch", is_active=True)
        db.add(target_branch)
        await db.flush()

        target_lead = Lead(
            branch_id=target_branch.id,
            tenant_id=target_tenant.id,
            wa_phone="+520000000002",
            name="Lead de TARGET — SI debe verse durante impersonacion",
        )
        db.add(target_lead)

        await db.commit()
        await db.refresh(platform_owner)
        await db.refresh(home_lead)
        await db.refresh(target_lead)

        return {
            "platform_owner_id": platform_owner.id,
            "home_tenant_id": home_tenant.id,
            "target_tenant_id": target_tenant.id,
            "home_lead_id": home_lead.id,
            "target_lead_id": target_lead.id,
        }


async def _cleanup(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(Tenant).where(
                Tenant.id.in_([ctx["home_tenant_id"], ctx["target_tenant_id"]])
            )
        )
        await db.commit()


async def _count_monthly_goals(tenant_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(MonthlyGoal).where(MonthlyGoal.tenant_id == tenant_id))).scalars().all()
        return len(rows)


def _goal_body() -> dict:
    today = date.today()
    return {
        "period_year": today.year,
        "period_month": today.month,
        "amount": "1000",
        "currency": "MXN",
        "dimension": "global",
    }


async def main() -> int:
    print("=" * 70)
    print("  test_impersonation.py — hallazgo #9, PERMISSIONS_DRIFT_BACKLOG.md")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []
    ctx = await _setup()

    try:
        normal_token = create_access_token({
            "sub": str(ctx["platform_owner_id"]),
            "tenant_id": str(ctx["home_tenant_id"]),
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            auth_normal = {"Authorization": f"Bearer {normal_token}"}

            # ── b) Obtener token de impersonación ─────────────────────────────
            r = await client.post(
                f"/api/platform/impersonate/{ctx['target_tenant_id']}",
                headers=auth_normal,
            )
            ok = r.status_code == 200
            results.append((
                "b. POST /api/platform/impersonate/{tenant_id} -> 200",
                ok, f"status={r.status_code} body={r.text[:300]}",
            ))
            if not ok:
                results.append(("ABORTADO — sin token de impersonacion no se puede seguir", False, "ver punto b arriba"))
                return _report(results)

            imp_token = r.json()["access_token"]
            auth_imp = {"Authorization": f"Bearer {imp_token}"}

            # ── c) GET /api/leads con token de impersonación ──────────────────
            r = await client.get("/api/leads", params={"all": "true"}, headers=auth_imp)
            if r.status_code == 200:
                ids = {item["id"] for item in r.json().get("items", [])}
                sees_target = str(ctx["target_lead_id"]) in ids
                sees_home = str(ctx["home_lead_id"]) in ids
                ok_c = sees_target and not sees_home
                detail = f"status=200 sees_target_lead={sees_target} sees_home_lead={sees_home} (esperado: True/False) total_items={len(ids)}"
            else:
                ok_c = False
                detail = f"status={r.status_code} body={r.text[:300]}"
            results.append((
                "c. GET /api/leads (token impersonación) devuelve datos del TENANT OBJETIVO, no del platform_owner",
                ok_c, detail,
            ))

            # ── d) POST mutante con token de impersonación -> 403 ─────────────
            goals_before = await _count_monthly_goals(ctx["target_tenant_id"])
            r = await client.post("/api/goals/monthly-goals", json=_goal_body(), headers=auth_imp)
            expected_detail = "Esta sesión de impersonación es de solo lectura."
            got_detail = None
            try:
                got_detail = r.json().get("detail")
            except Exception:
                pass
            goals_after = await _count_monthly_goals(ctx["target_tenant_id"])
            ok_d = r.status_code == 403 and got_detail == expected_detail and goals_after == goals_before
            results.append((
                "d. POST /api/goals/monthly-goals (token impersonación) -> 403, sin crear nada",
                ok_d,
                f"status={r.status_code} detail={got_detail!r} goals_before={goals_before} goals_after={goals_after}",
            ))

            # ── e) POST mutante con token NORMAL -> sigue funcionando ─────────
            goals_before_home = await _count_monthly_goals(ctx["home_tenant_id"])
            r = await client.post("/api/goals/monthly-goals", json=_goal_body(), headers=auth_normal)
            goals_after_home = await _count_monthly_goals(ctx["home_tenant_id"])
            ok_e = r.status_code == 200 and goals_after_home == goals_before_home + 1
            results.append((
                "e. POST /api/goals/monthly-goals (token NORMAL, sin impersonación) sigue funcionando (200, crea la meta)",
                ok_e,
                f"status={r.status_code} goals_before={goals_before_home} goals_after={goals_after_home}",
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
