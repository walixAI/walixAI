# Walix CRM — Blueprint de Arquitectura de Sistemas de IA

**Versión:** Sprint 6 (Jun 2026)
**Stack base:** Python 3.13 · FastAPI · PostgreSQL 16 + pgvector · Redis · APScheduler · Anthropic SDK · OpenAI SDK · Vite 5 · React 18

---

## 1. Vista General del Sistema

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CANAL DE ENTRADA                                  │
│                                                                             │
│   WhatsApp Business API (Meta)          Walix Web App (React 18)            │
│   POST /api/webhooks/whatsapp           Walix AI Bar  ⌘K                   │
│          │                                     │                            │
└──────────┼─────────────────────────────────────┼────────────────────────────┘
           │                                     │
           ▼                                     ▼
┌──────────────────────────┐         ┌──────────────────────────┐
│   BOT ENGINE (Haiku)     │         │   AI BAR (Haiku)         │
│   Conversación RAG       │         │   Comandos + Acciones    │
│   Calificación Lead      │         │   Insight de contexto    │
└──────────┬───────────────┘         └──────────┬───────────────┘
           │                                     │
           ▼                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CAPA DE DATOS (PostgreSQL 16)                       │
│                                                                             │
│  leads · conversations · messages · lead_activities · pipeline_stages       │
│  knowledge_chunks (pgvector) · lead_scores · agent_suggestions              │
│  daily_metrics · sentiment_snapshots · onboarding_drafts · users            │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CAPA DE AGENTES PROACTIVOS (APScheduler)                 │
│                                                                             │
│   follow_up · pipeline · closing (trigger) · config                        │
│   metrics_aggregator · sentiment_aggregator                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Subsistemas de IA — Detalle

### 2.1 Bot Conversacional RAG

**Archivo:** `app/ai/bot_engine.py`
**Modelo:** `claude-haiku-4-5-20251001` · max_tokens 300
**Flujo por mensaje entrante:**

```
WhatsApp webhook
      │
      ▼
  Normalizar teléfono MX (+52)
      │
      ▼
  get_or_create_lead()
      │
      ▼
  Cargar ai_config del branch (JSONB)
      │
      ▼
  get_conversation_context()
  ├── Redis HIT  →  historial JSON (TTL 24h)
  └── Redis MISS →  últimos N mensajes de DB (fallback)
      │
      ▼
  RAG retrieval (si knowledge base activa)
  ├── OpenAI embeddings (text-embedding-3-large 1536d)
  ├── Vector search: kc.embedding <=> query_vector  (pgvector cosine)
  ├── BM25 full-text: to_tsvector('spanish')
  └── Fusión RRF → top-K chunks (min_score 0.65)
      │
      ▼
  Construir system prompt 4 capas:
  ├── Capa 1: PERSONA (nombre, industria, tono)
  ├── Capa 2: CHANNEL_RULES (límites de WhatsApp)
  ├── Capa 3: RAG chunks relevantes
  └── Capa 4: Lead profile (score, etapa, datos recogidos)
      │
      ▼
  Claude Haiku → respuesta texto
      │
      ├── Persistir mensaje en DB (conversations · messages)
      ├── Actualizar Redis conv:{id}  TTL 24h
      ├── asyncio.create_task(qualify_lead)    ← no bloquea
      └── asyncio.create_task(calculate_lead_score) ← no bloquea
```

**Prompt de calificación** (`app/ai/qualifier.py`, Haiku, max_tokens 800):
- Evalúa campos requeridos según `ai_config.qualification.required_fields`
- Devuelve `{ status, qualification_score, fields_collected }`
- Al completar: `advance_lead_stage()` → mueve en pipeline, notifica asesor vía WA

---

### 2.2 Sistema RAG — Recuperación Híbrida

**Archivos:** `app/ai/ingestion.py` · `app/ai/retrieval.py` · `app/services/rag.py`

```
Ingesta de documentos:
  PDF/TXT/DOCX → chunking → OpenAI text-embedding-3-large (1536d)
                          → INSERT knowledge_chunks (embedding vector)

Retrieval en tiempo real:
  query_text
      │
      ├── embed(query) via OpenAI
      │
      ├── Vector search SQL:
      │     SELECT id, content, 1-(embedding <=> :vec) AS score
      │     FROM knowledge_chunks
      │     WHERE tenant_id = :tid
      │     ORDER BY embedding <=> :vec
      │     LIMIT 20
      │
      ├── BM25 search SQL:
      │     SELECT id, rank() OVER(ORDER BY ts_rank DESC) AS bm25_rank
      │     WHERE to_tsvector('spanish', content) @@ plainto_tsquery(:q)
      │
      └── RRF fusion:
            score = Σ 1/(k + rank_i)   k=60
            normalizado a [0, 1]
            filtro min_score = 0.65
            → top-K chunks para el system prompt
```

**Tablas:** `knowledge_documents` · `knowledge_chunks` (pgvector Vector(1536))

---

### 2.3 Predicción de Cierre (Lead Scoring)

**Archivo:** `app/services/prediction_service.py`
**Modelo:** `claude-haiku-4-5-20251001` · max_tokens 400
**Trigger:** `asyncio.create_task` tras cada mensaje (fire-and-forget)

```
calculate_lead_score(lead_id, tenant_id)
      │
      ▼
  Cargar lead + historial de mensajes (últimos 20)
      │
      ▼
  Claude Haiku + SCORING_SYSTEM_PROMPT
  Entrada:  datos del lead, conversación, etapa, sentimiento
  Salida JSON:
    {
      score: 0-100,
      main_reason: str,
      positive_factors: { items: [str, ...] },
      negative_factors: { items: [str, ...] },
      trend: "up" | "down" | "flat"
    }
      │
      ├── INSERT lead_scores (historial de puntuaciones)
      ├── UPDATE leads.current_score  ← cache en columna para evitar JOINs
      ├── UPDATE leads.current_score_trend
      │
      └── si score >= 70:
            _maybe_trigger_closing_agent()
            → asyncio.create_task(run_closing_agent)
```

**Frontend:**
- `LeadScoreBadge` en cada tarjeta del Kanban (semáforo + flecha trend)
- `LeadScoreGauge` en `LeadDetailSheet` (RadialBar + sparkline + factores)
- AI Bar proactiva: si `current_score >= 70` al abrir el sheet → `aiBar.addMessage` + `setOpen(true)`

---

### 2.4 AI Bar — Interfaz de Comandos en Lenguaje Natural

**Archivos:** `app/api/ai.py` · `app/ai/command_interpreter.py`
**Modelos:** `claude-haiku-4-5-20251001` · max_tokens 600 (comando) / 300 (insight)

#### Flujo de comando

```
Usuario escribe en AI Bar → POST /api/ai/command
      │
      ▼
  CommandInterpreter (Claude Haiku)
  Entrada: message + context (screen, branch_id, lead_id) + history[-10]
  Salida JSON:
    {
      intent_type: "consulta" | "accion",
      response_text: str,
      proposed_actions: [{ type, ...params }],
      suggested_actions: [str, ...]
    }
      │
      ├── intent_type = "consulta" → respuesta directa, sin ejecutar
      │
      └── intent_type = "accion"
            │
            ▼
          execute_actions() — RBAC por rol:
          ┌─────────────────────────────────────┐
          │ owner / gerente:                    │
          │   move_lead_stage                   │
          │   assign_lead                       │
          │   update_ai_config                  │
          │   create_alert_rule                 │
          │   navigate                          │
          │                                     │
          │ asesor / doctor:                    │
          │   move_lead_stage                   │
          │   assign_lead                       │
          │   navigate                          │
          └─────────────────────────────────────┘
```

#### Context Insight (GET /api/ai/context-insight)
- Claude Haiku analiza `screen` + datos del branch
- Devuelve: `{ insight, urgency: low|medium|high, suggested_actions }`
- Se muestra en el panel derecho de la AI Bar al abrirlo

---

### 2.5 Agentes Proactivos

**Directorio:** `app/agents/`
**Orquestador:** APScheduler AsyncIO · `app/services/scheduler.py`

Todos los agentes siguen el mismo contrato:
```
run_agent(branch_id) → int  (sugerencias creadas)
  ├── Consulta condición de disparo en DB
  ├── Si cumple → Claude genera texto de sugerencia
  ├── INSERT agent_suggestions  (tenant_id, branch_id, agent_type, expires_at+48h)
  ├── Notifica vía WhatsApp al usuario target (si tiene wa_phone)
  └── Retorna count de sugerencias creadas
```

| Agente | Modelo | Schedule | Condición de disparo | Target |
|--------|--------|----------|---------------------|--------|
| `follow_up_agent` | Haiku · 600tok | Cada hora 8-20h MX | Conversación activa, último mensaje > 24h, handler=BOT | asesor |
| `pipeline_agent` | Haiku · 500tok | Daily 7:00 AM MX | Leads estancados > N días en etapa, bajo conversion rate | gerente |
| `closing_agent` | **Sonnet 4.6** · 800tok | Trigger: score ≥ 70 | `prediction_service._maybe_trigger_closing_agent()` | asesor |
| `config_agent` | Haiku · 400tok | Lunes 8:00 AM MX | Branches con gaps en ai_config, alta tasa de escalaciones | owner |

**Ciclo de vida de una sugerencia:**
```
suggested → [aceptado por usuario] → confirmed → [executor.py] → executed
         → [rechazado]             → dismissed
         → [TTL 48h expirado]      → expired (job de limpieza)
         → [error en ejecución]    → failed → re-execute disponible (owner+)
```

**Executor (`app/agents/executor.py`):**
```
execute_suggestion(suggestion_id)
    │
    ▼
  _dispatch(agent_type)
  ├── follow_up  → _exec_follow_up()   : send_text_message al lead vía WA
  ├── pipeline   → _exec_pipeline()
  │     ├── reassign   : LeadActivity + assign_lead
  │     └── archive_stage : desactivar PipelineStage
  ├── closing    → _exec_closing()     : send propuesta personalizada al lead
  └── config     → _exec_config()      : UPDATE branch.ai_config
```

---

### 2.6 Motor de Métricas

**Archivos:** `app/services/metrics_engine.py` · `app/services/sentiment_aggregator.py`
**API:** `app/api/metrics.py` · Redis cache TTL 300s

```
┌──────────────────────────────────────────────────────────────┐
│                    JOBS PLANIFICADOS                         │
│                                                              │
│  _job_aggregate_metrics  →  cada hora                        │
│    aggregate_daily_metrics(branch_id, yesterday, db)         │
│    → UPSERT daily_metrics  (17 KPIs por branch/día)          │
│    → UNIQUE(branch_id, metric_date)                          │
│                                                              │
│  _job_calculate_sentiment  →  23:00 MX diario                │
│    calculate_sentiment_snapshot(branch_id, db)               │
│    → Pesos: interesado=1.0, urgente=0.8, neutral=0.5,        │
│             negativo=0.0                                      │
│    → UPSERT sentiment_snapshots (overall_score, by_stage,    │
│                                  by_agent, distribution)     │
└──────────────────────────────────────────────────────────────┘

Endpoints:
  GET /api/metrics/dashboard?period=week|month|quarter&compare=true
    → DashboardMetricsOut { current, previous, delta, daily[] }
    → Redis cache key: metrics:dashboard:{branch_id}:{period}:{compare}

  GET /api/metrics/sentiment
    → SentimentOut { current, trend, insight }

  GET /api/metrics/forecast
    → ForecastOut { pipeline_forecast{high,medium,low},
                    high_probability_leads[], at_risk_leads[] }
```

**Tabla `daily_metrics` — KPIs calculados:**
leads_created · leads_qualified · leads_won · leads_lost · messages_sent ·
messages_received · calls_logged · tasks_completed · quotes_sent ·
avg_first_response_sec · conversion_rate · metrics_by_agent (JSONB)

---

### 2.7 Dashboard por Rol

**Archivo:** `app/api/dashboard.py`
**Cache:** Redis TTL 300s · clave: `dashboard:{role}:{user_id}:{date}`

```
GET /api/dashboard
        │
        ├── platform_owner → 307 redirect a /api/platform/stats
        │
        ├── Leer Redis cache → HIT: return JSON
        │
        ├── it      → _it_dashboard()   : WA status, AI logs, webhook errors
        ├── owner   → _owner_dashboard(): multi-branch, MRR, conversion delta
        ├── gerente → _gerente_dashboard(): pipeline, team performance, sentiment
        └── asesor  → _asesor_dashboard(): my_leads, activity, suggestions
                │
                └── Escribir Redis cache (json.dumps default=str)
```

| Rol | Datos principales |
|-----|------------------|
| `asesor` | my_leads + scores, recent_activity, pending_suggestions, mini_pipeline |
| `gerente` | pipeline{total_active, by_stage}, team_performance[], sentiment_summary, at_risk_leads[] |
| `owner` | branches[], mrr_estimate, conversion_comparison{this_month/last_month}, cross_branch_suggestions[] |
| `it` | integrations{branches_with/without_wa}, ai_command_logs_24h, webhook_errors_24h, config_alerts[] |

---

### 2.8 Onboarding en Lenguaje Natural

**Archivo:** `app/api/onboarding.py`
**Modelo:** `claude-sonnet-4-6` · max_tokens 4096 (generate) / 2048 (refine)

```
POST /api/onboarding/generate
  Input: { branch_id, business_description, industry }
  │
  ▼
  INDUSTRY_TEMPLATES[industry] → estructura base
  Claude Sonnet 4.6 genera ai_config completo:
    { bot_name, persona, qualification.required_fields[],
      pipeline_stages[], knowledge_topics[], channel_rules }
  → INSERT onboarding_drafts (status=draft)

POST /api/onboarding/refine
  { draft_id, section, instruction } → Claude Sonnet refina sección

POST /api/onboarding/approve
  → UPDATE branch.ai_config = draft.generated_config
  → INSERT pipeline_stages[] en DB
  → branch.onboarding_status = "completed"
```

---

## 3. Capa de Infraestructura

### 3.1 Caché Redis — Resumen de keys

| Key pattern | TTL | Propósito |
|------------|-----|-----------|
| `conv:{conversation_id}` | 24h | Historial de mensajes por conversación |
| `metrics:dashboard:{branch_id}:{period}:{compare}` | 300s | Dashboard de métricas |
| `dashboard:{role}:{user_id}:{date}` | 300s | Dashboard por rol |

### 3.2 Jobs APScheduler (8 registrados)

| Job ID | Trigger | Función |
|--------|---------|---------|
| `daily_summaries` | Cada 1h | Resumen diario leads sin respuesta |
| `detect_unresponded` | Cada 30min | Detectar leads sin respuesta → alerta WA |
| `monthly_summaries` | 1ro de mes 9h MX | Resumen mensual por branch |
| `aggregate_metrics` | Cada hora (:00) | UPSERT daily_metrics para ayer |
| `calculate_sentiment` | 23:00 MX diario | UPSERT sentiment_snapshots |
| `follow_up_agent` | 8-20h MX, cada hora | Sugerencias follow-up leads inactivos >24h |
| `pipeline_agent` | 7:00 AM MX diario | Análisis salud del pipeline |
| `config_agent` | Lunes 8:00 AM MX | Detectar gaps en configuración del branch |

*`closing_agent` no usa scheduler — es trigger-based desde `prediction_service`.*

### 3.3 APIs Externas

| Servicio | SDK/Client | Uso |
|----------|-----------|-----|
| Anthropic | `AsyncAnthropic` | Bot RAG, scoring, agentes, AI Bar, onboarding |
| OpenAI | `AsyncOpenAI` | Embeddings (text-embedding-3-large 1536d) |
| Meta WhatsApp Business | `httpx` directo | Recepción webhooks, envío mensajes/templates, mark_as_read |

---

## 4. Modelo de Datos — Tablas de IA

```
tenants (1)
    └── branches (N)
            ├── leads (N)
            │      ├── conversations (1)
            │      │      └── messages (N)
            │      ├── lead_activities (N)
            │      ├── lead_scores (N) ──────────── historial de puntuaciones
            │      └── leads.current_score ←──────── cache última puntuación
            │
            ├── knowledge_documents (N)
            │      └── knowledge_chunks (N) ←── Vector(1536) pgvector
            │
            ├── agent_suggestions (N) ──────────── branch_id + tenant_id
            │      └── TTL 48h · lifecycle: suggested→confirmed→executed
            │
            ├── daily_metrics (N) ──────────────── UNIQUE(branch_id, date)
            ├── sentiment_snapshots (N) ─────────── UNIQUE(branch_id, date)
            ├── onboarding_drafts (N)
            ├── pipeline_stages (N)
            └── alert_rules (N)

users (N) ──── roles: platform_owner · owner · gerente · asesor · doctor · it · soporte
ai_command_logs (N) ──── auditoría de llamadas a la AI Bar
```

---

## 5. Selección de Modelos por Caso de Uso

| Caso de uso | Modelo | Por qué |
|-------------|--------|---------|
| Conversación WhatsApp tiempo real | Haiku 4.5 | Latencia <2s, alto volumen |
| AI Bar comando/acción | Haiku 4.5 | Respuesta rápida, JSON estructurado |
| AI Bar context-insight | Haiku 4.5 | Ligero, frecuente (cada apertura) |
| Lead scoring | Haiku 4.5 | Fire-and-forget, bajo costo, alta frecuencia |
| Follow-up agent | Haiku 4.5 | Texto corto, batch nocturno |
| Pipeline agent | Haiku 4.5 | Análisis tabular, batch diario |
| Config agent | Haiku 4.5 | Estructurado, semanal |
| **Closing agent** | **Sonnet 4.6** | Propuesta de venta → calidad > velocidad |
| **Onboarding generate** | **Sonnet 4.6** | Generación compleja de config JSON (4096 tok) |
| **Onboarding refine** | **Sonnet 4.6** | Razonamiento sobre instrucción + borrador |
| Calificación de leads | Haiku 4.5 | Post-mensaje, no bloquea respuesta |

---

## 6. Patrones de Diseño de IA Aplicados

**Fire-and-forget async tasks:** scoring y calificación se lanzan con `asyncio.create_task` desde `bot_engine` — el usuario recibe la respuesta de WhatsApp en <300ms mientras el scoring ocurre en background.

**Redis como hot path:** el historial de conversación viaja en Redis (TTL 24h) evitando queries a DB en cada mensaje. DB es solo el fallback y el registro permanente.

**Score cacheado en columna:** `leads.current_score` evita un JOIN con `lead_scores` en cada card del Kanban. El scoring actualiza ambas tablas (histórico + columna desnormalizada).

**Hybrid RAG con RRF:** combinación de búsqueda vectorial + BM25 fusionados con Reciprocal Rank Fusion. Más robusto que solo cosine similarity para queries cortas o sin contexto semántico claro.

**Agent suggestions como estado explícito:** las sugerencias tienen ciclo de vida completo en DB (no son notificaciones efímeras). Permite auditoría, re-ejecución, y la vista de repositorio en `/automations`.

**RBAC en acciones de AI Bar:** `execute_actions()` valida el rol del JWT antes de ejecutar cualquier acción. Asesor no puede `update_ai_config` aunque Claude lo proponga.

**Cache por usuario para dashboard:** la clave incluye `user_id` porque el asesor ve *sus* leads. Gerente/owner podrían compartir clave por branch, pero usar `user_id` elimina edge cases de multi-branch.
