# Auditoría: Opportunity vs Deal — ¿Está muerto Opportunity?

> Fecha: 2026-06-21. Solo lectura — no modifica nada.

---

## 1. Endpoints HTTP activos para Opportunity

Ambos routers están **registrados y activos** en `app/main.py` (líneas 68–69):

```python
app.include_router(opportunities.router, prefix="/api")      # /api/opportunities/*
app.include_router(opportunities_ai.router, prefix="/api")   # /api/opportunities/ai/*, /api/opportunities/{id}/ai/*
```

### `opportunities.py` — 13 endpoints (prefijo `/api/opportunities`)

| Método | Ruta | Función |
|---|---|---|
| GET | `/board` | Kanban por etapas |
| GET | `` (raíz) | Lista con filtros |
| POST | `` | Crear oportunidad |
| GET | `/forecast` | Pronóstico de cierre |
| GET | `/stale` | Oportunidades estancadas |
| GET | `/export.csv` | Exportar CSV |
| GET | `/{opp_id}` | Detalle |
| PATCH | `/{opp_id}` | Actualizar |
| PATCH | `/{opp_id}/stage` | Mover de etapa |
| POST | `/{opp_id}/lost` | Marcar perdida |
| POST | `/{opp_id}/won` | Marcar ganada |
| POST | `/bulk/stage` | Cambio masivo de etapa |
| POST | `/bulk/delete` | Borrado masivo |
| DELETE | `/{opp_id}` | Borrar |

### `opportunities_ai.py` — 4 endpoints adicionales

| Método | Ruta | Función |
|---|---|---|
| POST | `/ai/insights` | Health score + Haiku analysis (cache Redis 10min) |
| POST | `/ai/bulk-suggestions` | Encolar Celery para todas las opps de una branch |
| POST | `/{opp_id}/ai/next-step` | Siguiente paso IA, persiste en `opp.ai_suggestion` |
| POST | `/{opp_id}/ai/probability` | Predicción de probabilidad de cierre |

---

## 2. ¿El frontend llama a `/api/opportunities/*`?

**Sí, pero desde una ruta no navegable.** El frontend tiene DOS implementaciones de pipeline en paralelo:

| Ruta frontend | Componente | Modelo backend | En sidebar/nav |
|---|---|---|---|
| `/pipeline` | `pages/app/Pipeline.tsx` | **Deal** (`/api/pipeline/deals`, `/api/deals/*`) | ✅ Sí (`Sidebar.tsx` y `BottomNav.tsx`) |
| `/opportunities` | `features/pipeline/PipelinePage.tsx` | **Opportunity** (`/api/opportunities/*`) | ❌ No aparece en ningún nav |

El route `/opportunities` existe en `App.tsx` (línea 117) y tiene toda la UI implementada (`OpportunityStore`, `OppKanbanBoard`, `OpportunityDrawer`, `NuevaOportunidadModal`, etc.), pero **no está enlazado desde el sidebar ni desde ningún componente de navegación activo**. Es una ruta huérfana — accesible por URL directa, invisible para el usuario.

### Llamadas API desde `lib/api.ts` que aún apuntan a `/api/opportunities/*`:

```
getOpportunityBoard, createOpportunity, getOpportunity, updateOpportunity,
moveOpportunityStage, markOpportunityLost, markOpportunityWon,
bulkMoveStage, bulkDelete, deleteOpportunity, getOpportunityForecast,
getStaleOpportunities, exportCsv, getOppNextStep, getOppProbability,
getOppInsights, enqueueBulkSuggestions
```

---

## 3. ¿Los agentes Celery usan Opportunity o Deal?

**Los 6 agentes proactivos usan únicamente `Lead`, nunca `Opportunity` ni `Deal`:**

| Agente | Modelo que lee/escribe |
|---|---|
| `follow_up_agent` | `Lead`, `Conversation`, `Message`, `AgentSuggestion` |
| `pipeline_agent` | `Lead`, `PipelineStage`, `LeadActivity`, `AgentSuggestion` |
| `config_agent` | `PipelineStage`, `Lead`, `AgentSuggestion` |
| `closing_agent` | `Lead`, `Conversation`, `Message`, `AgentSuggestion` |
| `reactivation_agent` | `Lead`, `Conversation`, `Message`, `AgentSuggestion` |
| `profile_enrichment_agent` | `Lead`, `Conversation`, `Message`, `AgentSuggestion` |

**Excepción:** `opp_ai_tasks.py` (tarea Celery `generate_bulk_suggestions`) sí usa `Opportunity` directamente — es la tarea que alimenta el endpoint `POST /opportunities/ai/bulk-suggestions`.

---

## 4. ¿Hay datos reales en la tabla `opportunities`?

No es posible verificarlo sin conexión a la BD de Railway desde este entorno. Requiere:

```bash
psql $DATABASE_PUBLIC_URL -c "SELECT COUNT(*) FROM opportunities;"
```

Si el contador es 0, refuerza el caso de código muerto. Si hay filas, hay datos de usuario reales que habría que migrar antes de archivar.

---

## 5. ¿Conviven `opportunities` y `deals` en el esquema?

**Sí, son tablas completamente independientes.** El historial de migraciones lo confirma:

| Migración | Revisión | Qué crea |
|---|---|---|
| `r5s6t7u8v9w0_pipeline_opportunities.py` | Sprint ~12 | `opportunities`, `opportunity_stage_history`, `opportunity_activities` + RLS |
| `s6t7u8v9w0x1_sprint13a_deals.py` | Sprint 13A | `deals` + RLS (tabla nueva, no reemplaza nada) |
| `t7u8v9w0x1y2_sprint14a_deal_fields_and_history.py` | Sprint 14A | Columnas adicionales en `deals` + `deal_stage_history` |
| `u8v9w0x1y2z3_sprint14c1_stage_probability.py` | Sprint 14C | `probability_default` en `pipeline_stages` |
| `v9w0x1y2z3a4_sprint14c2_deal_owner.py` | Sprint 14C | `owner_id` en `deals` |

`deals` se añadió como entidad nueva sobre `opportunities` — no hubo `DROP TABLE opportunities` en ninguna migración. Ambas coexisten.

---

## 6. Veredicto

**Opportunity NO es código muerto trivial — es una implementación paralela completa que el frontend abandonó sin eliminar.**

| Aspecto | Estado |
|---|---|
| Endpoints backend activos | ✅ 17 rutas montadas y funcionales |
| Frontend con UI completa | ✅ Kanban, drawer, modales, store, AI panel |
| Enlazado desde la navegación | ❌ Ningún nav apunta a `/opportunities` |
| Usado por agentes Celery | Solo `opp_ai_tasks.generate_bulk_suggestions` |
| Usado por dashboard | ❌ El dashboard usa `Deal` |
| Modelo `Deal` lo reemplaza funcionalmente | ✅ Para el pipeline activo (`/pipeline`) |

### Qué implica archivar Opportunity

Para eliminar `Opportunity` de forma segura habría que:

1. Confirmar que `COUNT(*) FROM opportunities = 0` (sin datos de usuario)
2. Eliminar los routers `opportunities` y `opportunities_ai` de `main.py`
3. Eliminar `features/pipeline/` del frontend (la UI del Opportunity Kanban)
4. Eliminar las ~18 funciones de `lib/api.ts` que llaman a `/api/opportunities/*`
5. Eliminar `opportunityStore.ts` y la ruta `/opportunities` de `App.tsx`
6. Eliminar `opp_ai_tasks.py` o redirigirlo a `Deal`
7. Crear una migración `DROP TABLE opportunities, opportunity_stage_history, opportunity_activities`

Si la tabla está vacía y el equipo confirma que `/opportunities` nunca se usó en producción, el archivado es seguro. Si hay datos, se necesita una decisión sobre migración a `deals`.
