"""dashboard_widgets: ai_intelligence_section antes de task_cards en Principal

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-08-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "j5k6l7m8n9o0"
down_revision = "i4j5k6l7m8n9"
branch_labels = None
depends_on = None

# Reordena SOLO default_position (catálogo global dashboard_widgets) — no
# toca surface, no toca min_role, no toca ningún otro widget fuera de los
# que comparten panel Principal. La suite de regresión confirmó que
# "Inteligencia IA" vive correctamente en Principal (surface="principal",
# ver i4j5k6l7m8n9); lo único pedido acá es que aparezca antes de
# "Mis Tareas" (task_cards) en el orden default.
#
# _resolve_layout() en app/api/dashboard_widgets.py hace merge con
# dashboard_layouts guardado (scope user/role/tenant_default en cascada): un
# widget solo usa default_position cuando NO tiene una entrada explícita en
# el layout guardado del usuario. Por lo tanto este cambio:
#   - Tenants/usuarios sin layout guardado (nuevos) heredan el nuevo orden.
#   - Usuarios que ya reordenaron "Inteligencia IA" a mano vía CustomizeSheet
#     tienen una entrada explícita para esa key en su dashboard_layouts.items
#     -> esa posición guardada gana; este cambio de catálogo NO la pisa.
#   - Usuarios con un layout guardado ANTERIOR a que este widget existiera
#     (sin entrada para ai_intelligence_section) lo heredan en la nueva
#     posición, sin afectar las posiciones que sí guardaron explícitamente
#     para los demás widgets.
_NEW_POSITIONS = {
    "ai_intelligence_section": 2,
    "task_cards": 3,
    "recent_activity": 4,
    "proactive_briefing": 5,
    "ai_patterns": 6,
    "pipeline_by_stage_chart": 7,
    "deals_closed_timeline_chart": 8,
}
_OLD_POSITIONS = {
    "ai_intelligence_section": 8,
    "task_cards": 2,
    "recent_activity": 3,
    "proactive_briefing": 4,
    "ai_patterns": 5,
    "pipeline_by_stage_chart": 6,
    "deals_closed_timeline_chart": 7,
}


def _apply(positions: dict[str, int]) -> None:
    conn = op.get_bind()
    for key, pos in positions.items():
        conn.execute(
            sa.text("UPDATE dashboard_widgets SET default_position = :pos WHERE key = :key"),
            {"pos": pos, "key": key},
        )


def upgrade() -> None:
    _apply(_NEW_POSITIONS)


def downgrade() -> None:
    _apply(_OLD_POSITIONS)
