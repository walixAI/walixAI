"""
Regresión — Inteligencia IA del Dashboard (Prompt 7b).

Código auditado: app/api/metrics.py — GET /api/metrics/pipeline-intelligence
(NO vive bajo /api/dashboard/*, a pesar del nombre "dashboard intelligence"
en el prompt original — se confirmó leyendo app/main.py: el router de
metrics.py se monta con prefix="/api" y su propio prefix interno "/metrics").

Notas de auditoría:
  - `health_score` se calcula 100% en Python a partir de `stale_pct` y
    `bottleneck_names` (metrics.py:1120) — NUNCA llama a Claude. Se prueba
    forzando que la llamada a Anthropic falle y confirmando que el score
    sigue siendo el valor determinístico esperado.
  - `risks` y `executive_summary` SÍ vienen de Claude Haiku
    (`claude-haiku-4-5-20251001`, metrics.py:1236) parseando un bloque JSON
    de la respuesta. Se mockea `_anthropic.messages.create` — nunca se pega
    a la API real en estos tests.
  - Cache en Redis: clave `pipeline-intel:{tenant_id}:{branch_key}`,
    TTL=600s (metrics.py:1272). `force_refresh=True` bypassea la lectura de
    cache (sigue escribiendo al final).
  - Si la llamada a Claude lanza excepción, el código cae a
    `source="fallback"` y devuelve 200 con `executive_summary` fijo
    ("Análisis no disponible.") y `risks=[]` — nunca 500.
  - "Próximas a cerrar" (`closing_soon`): para cada pipeline, se busca la
    etapa `is_won=True` y se usa la etapa INMEDIATAMENTE ANTERIOR por
    `order_index` como "pre-ganado" (metrics.py:1158-1163) — no depende de
    un nombre de etapa fijo como "Negociación".
"""
from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.metrics as metrics_module
from app.core.redis import redis_client
from app.models.deal import Deal
from app.models.pipeline import PipelineStage


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _fake_anthropic_response(summary: str, risks: list[dict]) -> SimpleNamespace:
    payload = json.dumps({"summary": summary, "risks": risks})
    return SimpleNamespace(content=[SimpleNamespace(text=payload)])


@pytest.fixture()
def mock_claude_success(monkeypatch: pytest.MonkeyPatch):
    """Reemplaza _anthropic.messages.create por un AsyncMock que cuenta llamadas
    y devuelve una respuesta JSON válida — nunca pega a la API real."""
    mock = AsyncMock(
        return_value=_fake_anthropic_response(
            "Resumen ejecutivo simulado, health score saludable.",
            [{"title": "Riesgo simulado", "severity": "low", "detail": "Detalle simulado"}],
        )
    )
    monkeypatch.setattr(metrics_module._anthropic.messages, "create", mock)
    return mock


@pytest.fixture()
def mock_claude_failure(monkeypatch: pytest.MonkeyPatch):
    """Simula que la llamada a Anthropic explota — para probar el fallback."""
    mock = AsyncMock(side_effect=RuntimeError("simulated Anthropic outage"))
    monkeypatch.setattr(metrics_module._anthropic.messages, "create", mock)
    return mock


async def test_health_score_is_deterministic_without_claude(
    client: AsyncClient, deal: Deal, mock_claude_failure: AsyncMock, owner_token: str,
) -> None:
    """El health score no depende de Claude: sigue siendo correcto aunque la
    llamada al LLM falle por completo (mockeada para fallar explícitamente)."""
    r = await client.get("/api/metrics/pipeline-intelligence", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    body = r.json()

    # 1 deal activo (fixture `deal`), no stale, sin cuello de botella → stale_pct=0
    # → score = round(100 - 0*0.4 - 0*5) = 100
    assert body["pipeline_health"]["score"] == 100
    assert body["pipeline_health"]["status"] == "excellent"
    # Claude sí se intentó llamar (para risks/summary) pero falló → no afecta el score
    assert mock_claude_failure.await_count >= 1


async def test_risks_and_summary_come_from_mocked_claude(
    client: AsyncClient, deal: Deal, mock_claude_success: AsyncMock, owner_token: str,
) -> None:
    r = await client.get(
        "/api/metrics/pipeline-intelligence",
        params={"force_refresh": "true"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "live"
    assert body["executive_summary"] == "Resumen ejecutivo simulado, health score saludable."
    assert body["risks"] == [
        {"title": "Riesgo simulado", "severity": "low", "detail": "Detalle simulado"}
    ]
    mock_claude_success.assert_awaited_once()


async def test_llm_failure_returns_200_with_fallback_not_500(
    client: AsyncClient, deal: Deal, mock_claude_failure: AsyncMock, owner_token: str,
) -> None:
    r = await client.get(
        "/api/metrics/pipeline-intelligence",
        params={"force_refresh": "true"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "fallback"
    assert body["executive_summary"] == "Análisis no disponible."
    assert body["risks"] == []


async def test_cache_prevents_second_claude_call_within_ttl(
    client: AsyncClient, deal: Deal, mock_claude_success: AsyncMock, owner_token: str,
) -> None:
    """Segunda llamada dentro de los 600s de cache no vuelve a invocar a Claude."""
    r1 = await client.get("/api/metrics/pipeline-intelligence", headers=auth(owner_token))
    assert r1.status_code == 200, r1.text
    assert mock_claude_success.await_count == 1

    r2 = await client.get("/api/metrics/pipeline-intelligence", headers=auth(owner_token))
    assert r2.status_code == 200, r2.text
    assert r2.json() == r1.json()
    assert mock_claude_success.await_count == 1, (
        "La segunda llamada dentro del TTL de 600s no debería invocar a Claude de nuevo"
    )


async def test_force_refresh_bypasses_cache(
    client: AsyncClient, deal: Deal, mock_claude_success: AsyncMock, owner_token: str,
) -> None:
    r1 = await client.get("/api/metrics/pipeline-intelligence", headers=auth(owner_token))
    assert r1.status_code == 200, r1.text
    assert mock_claude_success.await_count == 1

    r2 = await client.get(
        "/api/metrics/pipeline-intelligence",
        params={"force_refresh": "true"},
        headers=auth(owner_token),
    )
    assert r2.status_code == 200, r2.text
    assert mock_claude_success.await_count == 2, (
        "force_refresh=true debe saltarse la lectura de cache y volver a llamar a Claude"
    )


async def test_closing_soon_uses_real_pre_won_stage(
    client: AsyncClient, db: AsyncSession, contact, stages: list[PipelineStage],
    tenant, owner_user, mock_claude_success: AsyncMock, owner_token: str,
) -> None:
    """`closing_soon` usa la etapa is_won=True y toma la inmediatamente anterior
    por order_index — en el fixture `stages`, esa es stages[1] ("Negociación"),
    no un nombre de etapa hardcodeado."""
    pre_won_stage = stages[1]
    assert stages[2].is_won is True and stages[2].order_index == 2
    assert pre_won_stage.order_index == 1

    closing_deal = Deal(
        tenant_id=tenant.id,
        lead_id=contact.id,
        pipeline_stage_id=pre_won_stage.id,
        title="Deal por cerrar",
        amount=Decimal("42000"),
        probability=pre_won_stage.probability_default,
        owner_id=owner_user.id,
    )
    db.add(closing_deal)
    await db.flush()

    r = await client.get(
        "/api/metrics/pipeline-intelligence",
        params={"force_refresh": "true"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    closing = r.json()["closing_soon"]
    assert any(d["id"] == str(closing_deal.id) and d["stage_name"] == pre_won_stage.name for d in closing)
