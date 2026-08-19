"""Copiloto — Fase 1, Parte C: helper para registrar consumo de tokens.

Inserta una fila en ai_token_usage (RLS estándar — el caller debe estar
en una sesión con app.current_tenant_id ya seteado para el tenant
correspondiente, igual que cualquier otro insert sobre una tabla de
tenant). Todavía no se llama desde ningún lado: no hay endpoint de chat
que "cuente" como parte de esta fase (Fase 1 es catálogo + schema). Queda
listo para que Fase 2 lo invoque después de cada llamada real a la API de
Anthropic (ej. dentro de app/ai/copilot_engine.py::run_copilot_turn,
usando response.usage.input_tokens / .output_tokens).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_token_usage import AITokenUsage


async def log_token_usage(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    source: str,
    model_used: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost_usd: Decimal,
    branch_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AITokenUsage:
    """Adds an AITokenUsage row to the session. Does NOT commit —
    the caller decides when (usually alongside its own transaction)."""
    row = AITokenUsage(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=user_id,
        source=source,
        model_used=model_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
    )
    db.add(row)
    await db.flush()
    return row
