"""test_roi.py — Sprint 11: verifica el endpoint ROI y la configuración de valor.

Checks:
  a) GET /api/metrics/roi?period=30 → status 200 y campos numéricos >= 0
  b) Todos los campos numéricos requeridos son >= 0
  c) conversion_rate está entre 0 y 100
  d) leads_by_source suma == leads_total
  e) PATCH /api/tenant/roi-config con revenue_per_conversion = 900 → 200
  f) GET /api/metrics/roi → estimated_revenue != null después de configurar
  g) PASS/FAIL global

Uso:
  cd backend
  .venv/bin/python scripts/test_roi.py [--email EMAIL] [--password PASSWORD]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = "http://localhost:8000"

_PASS = "✓ PASS"
_FAIL = "✗ FAIL"

failures: list[str] = []


def report(label: str, ok: bool, detail: str = "") -> None:
    tag = _PASS if ok else _FAIL
    if not ok:
        failures.append(label)
    line = f"  {tag}  {label}"
    if detail:
        line += f"\n         {detail}"
    print(line)


def get_credentials() -> tuple[str, str]:
    """Parse --email / --password from argv or use defaults."""
    args = sys.argv[1:]
    email = "owner@clinica.com"
    password = "walix2024"
    for i, a in enumerate(args):
        if a == "--email" and i + 1 < len(args):
            email = args[i + 1]
        elif a == "--password" and i + 1 < len(args):
            password = args[i + 1]
    return email, password


async def main() -> None:
    email, password = get_credentials()
    print(f"\n{'='*55}")
    print("  Walix Sprint 11 — ROI Dashboard Tests")
    print(f"{'='*55}\n")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        # ── Login ──────────────────────────────────────────────────────────────
        try:
            login_res = await client.post(
                "/api/auth/login",
                json={"email": email, "password": password},
            )
            login_res.raise_for_status()
            token = login_res.json()["access_token"]
        except Exception as exc:
            print(f"  {_FAIL}  LOGIN: {exc}")
            print(f"\n  → ¿Está corriendo el servidor en {BASE_URL}?\n")
            sys.exit(1)

        headers = {"Authorization": f"Bearer {token}"}

        # ── (a) GET /api/metrics/roi?period=30 ────────────────────────────────
        roi_res = await client.get("/api/metrics/roi?period=30", headers=headers)
        ok_a = roi_res.status_code == 200
        report("(a) GET /api/metrics/roi?period=30 → 200", ok_a, f"status={roi_res.status_code}")
        if not ok_a:
            print(f"\n       Detail: {roi_res.text[:300]}")

        roi: dict = roi_res.json() if ok_a else {}

        # ── (b) Campos numéricos >= 0 ─────────────────────────────────────────
        numeric_fields = [
            "leads_total", "bot_qualified", "bot_qualification_rate",
            "handoffs_executed", "converted", "conversion_rate",
            "bot_messages_sent", "estimated_minutes_saved", "estimated_hours_saved",
            "leads_waiting_response", "agent_suggestions_generated",
            "agent_suggestions_accepted", "agent_acceptance_rate",
        ]
        bad_fields: list[str] = []
        if roi:
            for field in numeric_fields:
                val = roi.get(field)
                if val is None or (isinstance(val, (int, float)) and val < 0):
                    bad_fields.append(f"{field}={val}")
        ok_b = ok_a and not bad_fields
        report(
            "(b) Todos los campos numéricos >= 0",
            ok_b,
            ("" if not bad_fields else f"Problemáticos: {', '.join(bad_fields)}"),
        )

        # ── (c) conversion_rate en [0, 100] ───────────────────────────────────
        conv_rate = roi.get("conversion_rate", -1) if roi else -1
        ok_c = ok_a and 0.0 <= conv_rate <= 100.0
        report("(c) conversion_rate entre 0 y 100", ok_c, f"valor={conv_rate}")

        # ── (d) leads_by_source suma == leads_total ───────────────────────────
        if roi:
            total = roi.get("leads_total", 0)
            source_sum = sum(roi.get("leads_by_source", {}).values())
            ok_d = source_sum == total
        else:
            ok_d = False
        report(
            "(d) leads_by_source suma == leads_total",
            ok_d,
            f"suma_fuentes={source_sum if roi else '?'}, leads_total={total if roi else '?'}",
        )

        # ── (e) PATCH /api/tenant/roi-config ──────────────────────────────────
        patch_res = await client.patch(
            "/api/tenant/roi-config",
            json={"revenue_per_conversion": 900},
            headers=headers,
        )
        ok_e = patch_res.status_code == 200
        report("(e) PATCH /api/tenant/roi-config revenue=900 → 200", ok_e, f"status={patch_res.status_code}")

        # ── (f) estimated_revenue != null después de configurar ───────────────
        roi2_res = await client.get("/api/metrics/roi?period=30", headers=headers)
        roi2: dict = roi2_res.json() if roi2_res.status_code == 200 else {}
        ok_f = roi2_res.status_code == 200 and roi2.get("estimated_revenue") is not None
        report(
            "(f) estimated_revenue != null tras configurar valor",
            ok_f,
            f"estimated_revenue={roi2.get('estimated_revenue')}",
        )

    # ── Resumen ────────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    if not failures:
        print("  ✓ TODOS LOS CHECKS PASARON — Sprint 11 ROI OK\n")
    else:
        print(f"  ✗ FALLOS ({len(failures)}): {', '.join(failures)}\n")
    print(f"{'='*55}\n")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    asyncio.run(main())
