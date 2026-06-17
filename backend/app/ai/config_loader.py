"""Branch AI configuration loader for Walix.

Resolution order for get_branch_config():
  1. branch.bot_system_prompt (Sprint 12 — generado/editado desde onboarding)
  2. branch.ai_config (custom JSONB) when onboarding_status == "active"
  3. INDUSTRY_TEMPLATES[branch.industry]  (default for that vertical)
  4. INDUSTRY_TEMPLATES["salud"]          (global fallback)

This module is the single point of truth for:
  - Building the 2-layer base system prompt consumed by bot_engine.py
  - Building the JSON schema string injected into qualification prompts
"""

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.industry_templates import INDUSTRY_TEMPLATES
from app.models.tenant import Branch


async def get_branch_config(branch_id: str | uuid.UUID, db: AsyncSession) -> dict[str, Any]:
    """Returns the effective ai_config for the branch.

    Uses the custom config when the branch has completed onboarding;
    falls back to the industry default (or salud) otherwise.
    """
    bid = uuid.UUID(str(branch_id)) if not isinstance(branch_id, uuid.UUID) else branch_id
    branch: Branch | None = await db.get(Branch, bid)

    if branch is None:
        return get_default_config("salud")

    # Sprint 12: bot_system_prompt tiene prioridad sobre ai_config legacy
    if branch.bot_system_prompt:
        base = get_default_config(branch.industry or "salud")
        config: dict[str, Any] = {**base, "bot_persona": {**base.get("bot_persona", {}), "system_prompt": branch.bot_system_prompt}}
        if branch.bot_qualification_questions:
            config["_qualification_questions"] = branch.bot_qualification_questions
        return config

    if branch.ai_config and branch.onboarding_status == "active":
        return branch.ai_config

    return get_default_config(branch.industry or "salud")


def get_default_config(industry: str) -> dict[str, Any]:
    """Returns the template for the given industry, or salud as fallback."""
    return INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["salud"])


def build_system_prompt(config: dict[str, Any]) -> str:
    """Builds the 2-layer base system prompt from an ai_config dict.

    Layer 1 — bot persona (full character, tone, restrictions, objectives).
    Layer 2 — WhatsApp channel rules (character limit, formatting, turn-taking).

    bot_engine.py appends layers 3 (RAG context) and 4 (lead profile) on top
    of this output before calling Claude.
    """
    persona: str = config["bot_persona"]["system_prompt"]
    max_chars: int = config["channel_rules"]["max_chars"]

    channel_rules = (
        "REGLAS DE CANAL WHATSAPP:\n"
        f"- Sin asteriscos ni markdown. Máximo {max_chars} caracteres.\n"
        "- Una pregunta a la vez.\n"
        "- Si no sabes algo, escala al humano."
    )

    extra: list[str] = config["channel_rules"].get("extra_rules", [])
    if extra:
        channel_rules += "\n" + "\n".join(f"- {rule}" for rule in extra)

    return f"{persona}\n\n{channel_rules}"


def build_qualification_json_schema(required_fields: list[dict[str, str]]) -> str:
    """Builds the JSON schema string for the qualification prompt.

    required_fields: industry-specific list of {"name": str, "description": str}.
    Four fixed output fields are appended automatically:
      qualification_status, qualification_score, missing_fields, escalation_reason.

    Returns the schema as an indented JSON string suitable for direct injection
    into a prompt template via {fields_schema}.
    """
    schema: dict[str, str] = {}

    for field in required_fields:
        schema[field["name"]] = field["description"]

    # Fixed output fields — always present regardless of industry
    schema["qualification_status"] = (
        '"calificado" si cumple todos los criterios, '
        '"no_calificado" si explícitamente no cumple, '
        '"incompleto" si falta información, '
        '"escalar" si hay urgencia o caso especial'
    )
    schema["qualification_score"] = "float de 0.0 a 1.0 según qué tan completa está la calificación"
    schema["missing_fields"] = "lista de strings con los campos que faltan por recopilar"
    schema["escalation_reason"] = "razón del escalado o null"

    return json.dumps(schema, indent=2, ensure_ascii=False)
