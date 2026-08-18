# Backlog: Drift entre modelos ORM y schema real

> Solo lectura — hallazgos de auditoría, ninguna acción tomada todavía.
> Antes de tocar cualquiera de estas tablas hace falta un Prompt 0
> dedicado para decidir, tabla por tabla, si el modelo está desactualizado
> o si el schema real tiene algo que no debería.

---

## Drift entre modelos ORM y schema real (detectado 2026-08-18)

Encontrado durante la Fase 1 del Copiloto, al verificar con
`alembic revision --autogenerate` que los modelos nuevos
(`PlatformAIModelConfig`, `AITokenUsage`) no generaran drift falso. El
mismo comando expuso drift preexistente y no relacionado en otras tablas,
documentado acá para una auditoría separada.

### A) Tablas no importadas en `alembic/env.py`

`autogenerate` las ve como "tabla completa a borrar" porque `Base.metadata`
nunca las carga — probablemente solo falta el import correspondiente en
`alembic/env.py` (mismo gap que tenían `platform_ai_config`/
`ai_token_usage` antes de la migración `r3s4t5u6v7w8`/`s4t5u6v7w8x9`, ya
corregido para esos dos).

- `dashboard_widgets`
- `dashboard_layouts`
- `message_templates`
- `dashboard_panels`

### B) Discrepancias reales entre modelo y DB

No es problema de import — el modelo declara algo distinto de lo que
existe en producción. Lista completa tal como la generó `autogenerate`
contra una scratch DB migrada a `head`:

**`activities`**
- Removed index `ix_activities_due_date`
- Removed index `ix_activities_lead_id_created_at`
- Added index `ix_activities_lead_id` (sobre `(lead_id,)`)
- Removed check constraint `ck_activities_activity_type`
- Removed check constraint `ck_activities_closed_via`
- Removed check constraint `ck_activities_task_kind`

**`ai_command_logs`**
- Removed index `ix_ai_command_logs_intent_type`

**`alert_rules`**
- Removed index `ix_alert_rules_alert_type`

**`deals`**
- Removed check constraint `ck_deals_amount_non_negative`
- Removed check constraint `ck_deals_probability`

**`failed_payments`**
- Removed index `ix_failed_payments_created_at`

**`failed_tasks`**
- Added column `failed_tasks.updated_at`
- Removed unique constraint `uq_failed_tasks_task_id`
- Changed index `ix_failed_tasks_task_id`: `unique=False` → `unique=True`

**`knowledge_chunks`**
- Removed index `idx_chunks_embedding`
- Removed index `idx_chunks_fts`

**`lead_tags`**
- Removed index `ix_lead_tags_lead_id`
- Removed index `ix_lead_tags_tag_id`

**`leads`**
- Removed check constraint `ck_leads_prospection_source`

**`onboarding_conversations`**
- Removed index `ix_onboarding_conversations_tenant_session_turn`
- Added index `ix_onboarding_conversations_session_id`
- Added index `ix_onboarding_conversations_tenant_id`

**`pipeline_stages`**
- Type change: `probability_default` de `SMALLINT()` a `Integer()`
- Removed index `uq_pipeline_stage_key`

**`saved_views`**
- Removed unique constraint `uq_saved_views_user_name`
- Removed check constraint `ck_saved_views_view_mode`

**`subscriptions`**
- Removed index `ix_subscriptions_status`
- Removed unique constraint `uq_subscriptions_stripe_sub_id`
- Changed index `ix_subscriptions_stripe_subscription_id`: `unique=False` → `unique=True`

**`support_sessions`**
- Removed index `ix_support_sessions_status`

**`tags`**
- Removed unique constraint `uq_tags_tenant_name`

### Cómo se generó esta lista

```
1. Scratch DB migrada a head (incluye r3s4t5u6v7w8 y s4t5u6v7w8x9).
2. ALEMBIC_DATABASE_URL=<scratch> alembic revision --autogenerate -m "..."
3. Se leyó el log de alembic.autogenerate.compare.* y el archivo de
   migración generado; se descartó el archivo generado (no se commiteó
   ninguna migración de este chequeo).
```
