# Inventario del sistema de IA / agentes proactivos

> Generado: 2026-06-21. Solo lectura — no modifica nada.

---

## 1. Modelo `agent_suggestions`

| Columna | Tipo | Nullable | Notas |
|---|---|---|---|
| `id` | UUID | NO | PK, heredado de Base |
| `tenant_id` | UUID → `tenants.id` | NO | CASCADE, indexed |
| `branch_id` | UUID → `branches.id` | SÍ | SET NULL, indexed |
| `agent_type` | String(50) | NO | `follow_up \| pipeline \| closing \| config \| reactivation \| profile_enrichment` |
| `trigger_description` | Text | NO | Descripción corta del trigger (≤80 chars) |
| `suggestion_text` | Text | NO | Texto visible al usuario |
| `action_payload` | JSONB | SÍ | Contiene `lead_id`, `message`, `proposal_text`, etc. según agente |
| `target_role` | String(30) | NO | `asesor \| gerente \| owner` — a quién va dirigida |
| `target_user_id` | UUID → `users.id` | SÍ | SET NULL; null = broadcast a todos con `target_role` |
| `status` | String(20) | NO | `suggested \| accepted \| confirmed \| executed \| dismissed \| expired \| failed` |
| `execution_result` | JSONB | SÍ | Resultado tras ejecutar |
| `error_detail` | Text | SÍ | Detalle si status=failed |
| `responded_at` | DateTime TZ | SÍ | Momento en que el usuario confirmó/descartó |
| `expires_at` | DateTime TZ | NO | server_default: NOW() + 48h |
| `created_at` / `updated_at` | DateTime TZ | NO | Heredado de Base |

**Vínculo a leads/deals:** No hay `lead_id` ni `deal_id` como columnas directas. El `lead_id` vive dentro de `action_payload` como `{"lead_id": "<uuid>"}`. No hay ningún vínculo a la tabla `deals`. Las sugerencias del pipeline de oportunidades se manejan con campos inline en el modelo `Opportunity` (`ai_suggestion`, `ai_suggestion_urgency`, `urgency_score`) — no van a `agent_suggestions`.

---

## 2. Agentes proactivos

| Agente | Alcance | Trigger Celery | Qué analiza | Qué genera | `target_role` |
|---|---|---|---|---|---|
| `follow_up` | por branch | Cada 2h, 8am–8pm | Leads con conversación activa (bot) sin mensajes >24h | Sugerencia de re-engagement + mensaje WA draft | `asesor` |
| `pipeline` | por branch | Diario 7am | Etapas con >40% leads estancados >7 días; asesores con conversión <15% | Una acción correctiva al gerente: `create_task \| reassign \| archive_stage` | `gerente` |
| `config` | por branch | Lunes 8am (semanal) | Etapas sin actividad de `STAGE_CHANGE` en 30+ días | Sugerencia para desactivar etapas muertas | `owner` |
| `closing` | por branch | Diario 9am | Leads con `current_score >= 70` y sin `QUOTE` activity en 5 días | Propuesta de cierre + avanza lead a siguiente etapa al ejecutarse | `asesor` |
| `reactivation` | por tenant | Diario 10am | Leads sin terminal status, `updated_at < 30 días`, con ≥1 mensaje previo | Mensaje de reactivación personalizado | `asesor` |
| `profile_enrichment` | por tenant | Cada 72h | Leads sin `company` pero con ≥3 mensajes de conversación | Sugerencia para rellenar el campo empresa | `asesor` |

Todos escriben filas en `agent_suggestions`. La ejecución real (envío WA, reasignación, archivar etapa) ocurre cuando el usuario confirma → `POST /confirm` → Celery `execute_suggestion_task` → `executor.py/_dispatch()`.

---

## 3. Endpoints relacionados con IA / sugerencias

### `AgentSuggestion` — `/api/agents/…`

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/agents/suggestions` | Lista sugerencias activas del usuario actual (filtra por `target_user_id == me` OR `target_role == mi rol`). Expira in-band las caducadas antes de responder. |
| POST | `/api/agents/suggestions/{id}/confirm` | Marca `status=confirmed` + encola `execute_suggestion_task` en Celery. Devuelve `202`. |
| POST | `/api/agents/suggestions/{id}/dismiss` | Marca `status=dismissed` con razón opcional. |

No existen endpoints para: filtrar por `lead_id`/`deal_id`, disparar un agente on-demand sobre leads, ni listar historial (dismissed/executed).

### Opportunities AI — `/api/opportunities/…`

| Método | Ruta | Qué hace | Modelo |
|---|---|---|---|
| POST | `/api/opportunities/ai/insights` | Health score (0–100) + summary + risks + recommendations para una branch. Señales rule-based + Haiku. Cache Redis 10min. | Haiku |
| POST | `/api/opportunities/ai/bulk-suggestions` | Encola Celery `generate_bulk_suggestions` para todas las opps abiertas de una branch. `202 Accepted`. | — (enqueue) |
| POST | `/api/opportunities/{opp_id}/ai/next-step` | Genera next-step para una opp, persiste en `opp.ai_suggestion` + crea `OpportunityActivity`. | Haiku |
| POST | `/api/opportunities/{opp_id}/ai/probability` | Predice probabilidad de cierre (0–100) + señales. Read-only, no modifica la opp. | Haiku |

---

## 4. Salud del pipeline en backend

**Existe, pero solo para el pipeline de Oportunidades.** El endpoint `POST /api/opportunities/ai/insights` calcula:

- `health_score` = `100 − (stale_pct × 0.4) − (bottleneck_stages × 5)` — puro SQL
- Luego Haiku genera `summary`, `risks[]`, `recommendations[]` a partir de esas señales
- Resultado cacheado en Redis con TTL de 10 minutos

Para el **pipeline de Leads** (Kanban sprints 13–14), no hay endpoint de salud equivalente. El `pipeline_agent` (Celery, diario) sí analiza bottlenecks y estancamiento, pero solo genera una `AgentSuggestion` interna — no hay ruta HTTP que devuelva ese análisis bajo demanda.

---

## 5. Modelo Claude por agente

| Agente / componente | Modelo | Ubicación del prompt |
|---|---|---|
| `follow_up` | `claude-haiku-4-5-20251001` | `app/ai/prompts.py` → `FOLLOW_UP_AGENT_PROMPT` |
| `pipeline` | `claude-haiku-4-5-20251001` | `app/ai/prompts.py` → `PIPELINE_AGENT_PROMPT` |
| `config` | `claude-haiku-4-5-20251001` | `app/ai/prompts.py` → `CONFIG_AGENT_PROMPT` |
| `closing` | **`claude-sonnet-4-6`** | `app/ai/prompts.py` → `CLOSING_AGENT_PROMPT` |
| `reactivation` | `claude-haiku-4-5-20251001` | Inline `_SYSTEM_PROMPT` en `reactivation_agent.py` |
| `profile_enrichment` | `claude-haiku-4-5-20251001` | Inline `_SYSTEM_PROMPT` en `profile_enrichment_agent.py` |
| Opp insights | `claude-haiku-4-5-20251001` | Inline f-string en `opportunities_ai.py:pipeline_insights()` |
| Opp next-step | `claude-haiku-4-5-20251001` | Inline f-string en `opportunities_ai.py:next_step()` |
| Opp probability | `claude-haiku-4-5-20251001` | Inline f-string en `opportunities_ai.py:predict_probability()` |
| Opp bulk suggestions (Celery) | `claude-haiku-4-5-20251001` | Inline f-string en `opp_ai_tasks.py` |

Solo `closing_agent` usa Sonnet — genera propuestas de cierre que se envían directamente al cliente vía WhatsApp.
