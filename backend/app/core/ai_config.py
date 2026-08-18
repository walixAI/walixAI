"""Copiloto — Fase 1, Parte B: resuelve qué modelo de Claude usar por tier.

Fuente de verdad: la tabla platform_ai_model_config (raíz, sin RLS —
solo el platform_owner la escribe, vía el endpoint de Fase 7). Este
helper es de solo lectura y es lo que app/ai/copilot_engine.py consume
en vez de tener el modelo hardcodeado en una constante de módulo.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_ai_config import PlatformAIModelConfig

logger = logging.getLogger(__name__)

# Fallback si la tabla todavía no fue migrada/sembrada en este entorno, o si
# el tier pedido no tiene fila — nunca dejar al caller sin un modelo.
_FALLBACK_MODEL: dict[str, str] = {
    "simple": "claude-haiku-4-5-20251001",
    "compleja": "claude-sonnet-4-6",
}


async def get_model_for_tier(tier: str, db: AsyncSession) -> str:
    """Returns the configured model_name for `tier` ('simple' | 'compleja').

    Falls back to a hardcoded default (matching the migration's own seed
    values) if the row is missing or the query fails — a copiloto request
    should never break because platform_ai_model_config is momentarily
    unavailable (e.g. the table doesn't exist yet in an environment where
    this code deployed before migration r3s4t5u6v7w8 ran).

    The query runs inside a SAVEPOINT (db.begin_nested()): `db` is the same
    session used for the rest of the request (get_db()), so if the SELECT
    fails because the relation doesn't exist, Postgres aborts the whole
    transaction until a ROLLBACK — a bare try/except around db.execute()
    catches the Python exception but leaves the session's transaction
    poisoned, breaking every subsequent statement in this same request
    (including the eventual commit). begin_nested() rolls back only the
    savepoint on error, leaving the outer transaction/session healthy.
    """
    model_name: str | None = None
    try:
        async with db.begin_nested():
            model_name = (
                await db.execute(
                    select(PlatformAIModelConfig.model_name).where(
                        PlatformAIModelConfig.tier == tier
                    )
                )
            ).scalar_one_or_none()
    except Exception:
        logger.exception("get_model_for_tier: query failed for tier=%s", tier)
        model_name = None

    if model_name:
        return model_name

    fallback = _FALLBACK_MODEL.get(tier)
    if fallback is None:
        raise ValueError(f"Unknown tier '{tier}' and no fallback model configured")
    logger.warning(
        "get_model_for_tier: no row for tier=%s — using fallback %s", tier, fallback
    )
    return fallback
