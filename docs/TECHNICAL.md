# Walix CRM — Documentación Técnica

**Versión:** Sprint 8B · Junio 2026  
**Stack:** Python 3.13 · FastAPI · PostgreSQL 16 + pgvector · Redis · React 18 · Vite · Zustand · Anthropic SDK · Langfuse

---

## Índice

1. [Visión General](#1-visión-general)
2. [Arquitectura del Sistema](#2-arquitectura-del-sistema)
3. [Backend](#3-backend)
4. [Frontend](#4-frontend)
5. [Modelos de Datos](#5-modelos-de-datos)
6. [API Reference](#6-api-reference)
7. [Sistema de IA](#7-sistema-de-ia)
8. [Industry Templates](#8-industry-templates)
9. [Multi-tenancy y Seguridad](#9-multi-tenancy-y-seguridad)
10. [Configuración e Infraestructura](#10-configuración-e-infraestructura)
11. [Desarrollo Local](#11-desarrollo-local)
12. [Historial de Sprints](#12-historial-de-sprints)

---

## 1. Visión General

Walix es un **CRM conversacional sobre WhatsApp** dirigido a PyMEs mexicanas. El producto centraliza la gestión de leads/contactos capturados vía WhatsApp Business API y Meta Ads en un solo workspace multi-sucursal, con automatizaciones de IA (Claude) para calificación, seguimiento y análisis.

**Propuesta de valor central:**
- Un número de WhatsApp como canal principal de captación y atención
- Bot conversacional que califica leads con preguntas dinámicas por industria
- CRM visual con pipeline Kanban, score de calificación e historial completo
- AI Bar (⌘K) para ejecutar comandos en lenguaje natural
- Industry Templates que adaptan toda la nomenclatura de la UI al giro del negocio

**Primer cliente:** Clínica de Endocrinología Pediátrica (clínica beta)

---

## 2. Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                        CANALES DE ENTRADA                       │
│                                                                 │
│  WhatsApp Business API (Meta)        Walix Web App (React 18)  │
│  POST /api/webhooks/whatsapp         http://localhost:3000      │
└──────────────┬──────────────────────────────┬──────────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────┐    ┌─────────────────────────────┐
│   BOT ENGINE             │    │   AI BAR (⌘K)               │
│   Claude Haiku           │    │   CommandInterpreter         │
│   RAG + calificación     │    │   ContactExecutor            │
│   Multi-turno WA         │    │   ContextInsight             │
└──────────┬───────────────┘    └──────────────┬──────────────┘
           │                                   │
           ▼                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│               FastAPI (Python 3.13) — /backend/app              │
│                                                                 │
│  Auth · Leads · Contacts · Pipeline · Dashboard · Agents        │
│  Metrics · Onboarding · Platform · KB · Automations · Tags      │
└──────────────────────────────┬──────────────────────────────────┘
                               │
         ┌─────────────────────┼──────────────────┐
         ▼                     ▼                  ▼
┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐
│  PostgreSQL 16  │  │  Redis (Upstash) │  │  Langfuse      │
│  + pgvector     │  │  Caching / Cola  │  │  Observability │
│  Row-Level Sec. │  │                  │  │  LLM traces    │
└─────────────────┘  └─────────────────┘  └────────────────┘
```

**Despliegue:**
- Backend: Railway (auto-deploy en push a `main`)
- Frontend: Vercel (auto-deploy `main`)
- DB/Redis: Railway Postgres + Upstash Redis

---

## 3. Backend

### 3.1 Estructura de Directorios

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORS, middleware
│   ├── core/
│   │   ├── config.py            # Pydantic Settings (env vars)
│   │   ├── database.py          # AsyncSession, get_db, RLS helpers
│   │   ├── redis.py             # Redis client
│   │   └── security.py          # JWT, bcrypt, verify_token
│   ├── models/                  # SQLAlchemy ORM models (22 archivos)
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── api/                     # FastAPI routers (23 archivos)
│   ├── services/                # Lógica de negocio (11 servicios)
│   ├── agents/                  # Agentes autónomos (6 agentes + executor)
│   ├── ai/                      # Módulos de IA/LLM (10 archivos)
│   ├── industry_templates/      # Catálogo de templates por vertical
│   ├── middleware/              # TenantContextMiddleware
│   └── tasks/                  # APScheduler background tasks
├── alembic/
│   ├── env.py
│   └── versions/                # 22 migraciones
├── scripts/                     # Utilidades: seed, tests, backfill
├── requirements.txt
└── .env
```

### 3.2 Módulos API (`/app/api/`)

| Archivo | Prefijo | Descripción |
|---|---|---|
| `auth.py` | `/api/auth` | Login, register, `/me` |
| `leads.py` | `/api/leads` | CRUD leads, conversación, handoff, score |
| `contacts.py` | `/api/v1/contacts` | CRUD contactos, bulk, import/export CSV |
| `activities.py` | `/api/v1/contacts/{id}/activities` | Actividades por contacto |
| `saved_views.py` | `/api/v1/contacts/views` | Vistas guardadas de filtros |
| `tags.py` | `/api/v1/tags` | Gestión de etiquetas |
| `pipeline.py` | `/api/pipeline` | Board Kanban |
| `branches.py` | `/api/branches` | Sucursales, bot-config, Meta integration |
| `dashboard.py` | `/api/dashboard` | Métricas role-aware |
| `metrics.py` | `/api/metrics` | Dashboard analítico, forecast, sentimiento |
| `agents.py` | `/api/agents` | Sugerencias de agentes IA |
| `automations.py` | `/api/automations` | Gestión de automatizaciones |
| `ai.py` | `/api/ai` | AI Bar command, context-insight |
| `onboarding.py` | `/api/onboarding` | Draft, refine, approve (legacy) |
| `industry_onboarding.py` | `/api/v1/onboarding` | Analyze, confirm (Sprint 8B) |
| `platform.py` | `/api/platform` | Stats, tenants, impersonation (platform owner) |
| `support.py` | `/api/support` | Soporte técnico con sesión temporal |
| `webhooks.py` | `/api/webhooks` | Meta/WhatsApp webhook handler |
| `kb.py` | `/api/kb` | Reindexación y estado del Knowledge Base |
| `health.py` | `/health` | Health check (Postgres + Redis) |
| `users.py` | `/api/users`, `/api/branches/{id}/team` | Gestión de equipo |

### 3.3 Servicios (`/app/services/`)

| Servicio | Responsabilidad |
|---|---|
| `industry_inference.py` | Infiere industry_key desde descripción libre; keyword match + Claude Haiku |
| `tenant_setup.py` | Aplica Industry Template al tenant: actualiza campos, recrea pipeline stages |
| `rag.py` | Recuperación de contexto del Knowledge Base (pgvector) para el bot |
| `whatsapp.py` | Envío de mensajes y templates vía Meta WhatsApp Business API |
| `metrics_engine.py` | Cálculo de KPIs diarios, conversión, tiempo de respuesta |
| `sentiment_aggregator.py` | Snapshot de sentimiento por periodo/sucursal |
| `activity_service.py` | Registro y consulta de actividades sobre leads |
| `alert_generator.py` | Generación de alertas automáticas (riesgo, inactividad) |
| `prediction_service.py` | Forecast de ventas basado en score y etapa |
| `scheduler.py` | APScheduler: tareas periódicas (métricas, alertas, score) |

### 3.4 Agentes Autónomos (`/app/agents/`)

Los agentes son módulos que consumen datos del CRM y generan `AgentSuggestion` records, que se exponen vía `/api/agents/suggestions` y se muestran en la UI como tarjetas de automatización.

| Agente | Trigger | Acción |
|---|---|---|
| `closing_agent.py` | Lead calificado en última etapa > N días | Sugerencia de cierre |
| `follow_up_agent.py` | Sin actividad > umbral de días | Sugerencia de reactivación |
| `pipeline_agent.py` | Lead estancado en etapa | Sugerencia de avance de etapa |
| `profile_enrichment_agent.py` | Lead sin datos completos | Solicitud de datos faltantes |
| `reactivation_agent.py` | Lead marcado como perdido | Campaña de win-back |
| `config_agent.py` | Cambios de configuración de bot | Validación y propagación |
| `executor.py` | Disparado por scheduler | Ejecuta todos los agentes activos |

### 3.5 Middleware

**`TenantContextMiddleware`** — Extrae `tenant_id` del JWT en cada request y llama `SET LOCAL app.tenant_id = '...'` en PostgreSQL para activar las políticas de Row-Level Security antes de cualquier query.

### 3.6 Row-Level Security (RLS)

Todas las tablas con `tenant_id` tienen políticas de RLS que filtran automáticamente por el valor de `app.tenant_id` configurado por el middleware. Esto garantiza aislamiento de datos entre tenants incluso ante bugs de capa de aplicación.

---

## 4. Frontend

### 4.1 Estructura de Directorios

```
frontend/src/
├── pages/
│   ├── Login.tsx                # /login
│   ├── Register.tsx             # /register
│   ├── NotFound.tsx             # *
│   ├── dashboard/
│   │   └── DashboardPage.tsx    # /dashboard — métricas role-aware
│   ├── contacts/
│   │   ├── index.tsx            # /contacts — lista + filtros + vistas
│   │   └── [id].tsx             # /contacts/:id — detalle 3 columnas
│   ├── app/
│   │   ├── Pipeline.tsx         # /pipeline — Kanban
│   │   ├── Settings.tsx         # /settings
│   │   └── Whatsapp.tsx         # /whatsapp
│   ├── team/TeamPage.tsx        # /settings/team
│   ├── forecast/ForecastPage.tsx# /forecast
│   ├── automations/             # /automations
│   ├── onboarding/
│   │   ├── OnboardingWizard.tsx # /onboarding/new
│   │   └── PreviewPage.tsx      # /onboarding/preview/:draftId
│   └── platform/
│       └── PlatformDashboard.tsx# /platform (platform_owner only)
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx        # Shell con sidebar + topbar
│   │   ├── Sidebar.tsx          # Nav lateral (icon-only colapsable)
│   │   ├── BottomNav.tsx        # Nav mobile (4 ítems)
│   │   ├── TopBar.tsx           # Search AI Bar + avatar
│   │   ├── ProtectedRoute.tsx   # Guard: loading → spinner, no user → /login
│   │   └── ImpersonationBanner.tsx
│   ├── contacts/
│   │   ├── ContactsPageHeader.tsx   # h1 dinámico, botón "Nuevo X"
│   │   ├── ContactsFilters.tsx      # Search + filtros expandibles
│   │   ├── ContactsListView.tsx     # Tabla de contactos
│   │   ├── ContactsKanbanView.tsx   # Vista Kanban por status
│   │   ├── ContactsCardsView.tsx    # Vista tarjetas
│   │   ├── ContactsViewToggle.tsx   # Toggle lista/kanban/cards
│   │   ├── SavedViewDialog.tsx      # Modal guardar/editar vista
│   │   ├── SavedViewsSidebar.tsx    # Sidebar de vistas guardadas
│   │   └── detail/
│   │       ├── ContactLeftPanel.tsx  # Datos del contacto + etiquetas
│   │       ├── ContactTabConversaciones.tsx
│   │       └── ContactRightPanel.tsx # Oportunidades
│   ├── pipeline/LeadDetailSheet.tsx
│   ├── ai/AIPanel.tsx               # AI Bar modal (⌘K)
│   ├── ui/
│   │   ├── ContactStatusBadge.tsx   # Badge dinámico con colores del tenant
│   │   └── [shadcn components]
│   └── walix/
│       ├── Logo.tsx
│       ├── Badge.tsx (WBadge)
│       └── LoadingSpinner.tsx
├── hooks/
│   ├── useAuth.ts           # useInitAuth (carga /me en mount), useAuth
│   ├── useTenantLabels.ts   # Lee store y expone entity/entities/statuses
│   ├── useMobile.ts
│   └── useToast.ts
├── store/
│   └── auth.ts              # Zustand: user, tenant, entityName, entityPlural, contactStatuses
├── lib/
│   ├── api.ts               # Cliente HTTP fetch + todos los tipos TypeScript
│   ├── queries/
│   │   ├── contacts.ts      # React Query para /v1/contacts
│   │   ├── saved_views.ts   # React Query para /v1/contacts/views
│   │   └── tags.ts
│   └── utils.ts             # cn(), fechas, helpers
└── App.tsx                  # Router, ProtectedRoute, lazy loading
```

### 4.2 Estado de Autenticación

**Zustand Store** (`/store/auth.ts`):

```typescript
interface AuthState {
  user: WalixUser | null
  tenant: TenantData | null
  loading: boolean
  // Campos del Industry Template (derivados de tenant)
  entityName: string        // "Paciente" | "Alumno" | "Contacto" ...
  entityPlural: string      // "Pacientes" | "Alumnos" | "Contactos" ...
  contactStatuses: Array<{ key: string; label: string; color: string }>
  // Actions
  setUser, setTenant, setEntityName, setEntityPlural, setContactStatuses
  setLoading, logout
}
```

`setTenant()` es el único setter que necesitas llamar: deriva automáticamente `entityName`, `entityPlural` y `contactStatuses` del objeto `TenantData`.

**Flujo de hidratación:**

```
App mount
  └─ useInitAuth() [useEffect once]
       ├─ getToken() → localStorage.getItem('walix_token')
       ├─ api.me() → GET /auth/me
       │     └─ { user: WalixUser, tenant: TenantData }
       ├─ setUser(data.user)
       └─ setTenant(data.tenant)   ← puebla entityName + contactStatuses

Login/Register
  └─ api.login() / api.register()
       ├─ setToken(access_token)
       ├─ api.me()          ← segundo call para obtener tenant
       ├─ setUser(data.user)
       └─ setTenant(data.tenant)
```

### 4.3 Hook `useTenantLabels`

Centraliza todos los labels dinámicos. **Siempre usarlo en componentes, nunca leer del store directamente.**

```typescript
const {
  entity,                   // "Paciente"
  entities,                 // "Pacientes"
  newEntityLabel,           // "Nuevo Paciente"
  addEntityLabel,           // "Agregar Paciente"
  searchEntityPlaceholder,  // "Buscar Pacientes..."
  emptyStateLabel,          // "No hay Pacientes aún"
  totalLabel(n),            // "7 Pacientes" / "1 Paciente"
  statuses,                 // [{key, label, color}, ...]
  getStatusLabel(key),      // "key" → "Label legible"
  getStatusColor(key),      // "key" → "#hexcolor"
} = useTenantLabels()
```

### 4.4 Nomenclatura Dinámica — Componentes

| Componente | Labels dinámicos usados |
|---|---|
| `Sidebar.tsx` | `entities` (nav item label) |
| `BottomNav.tsx` | `entities` (mobile nav) |
| `ContactsPageHeader.tsx` | `entities`, `newEntityLabel`, `totalLabel` |
| `ContactsFilters.tsx` | `statuses`, `searchEntityPlaceholder` |
| `ContactsListView.tsx` | `entity` (columna "Paciente") |
| `ContactStatusBadge.tsx` | `statuses` (color + label por key) |
| `contacts/[id].tsx` | `entity`, `entities` (breadcrumb, error states) |

---

## 5. Modelos de Datos

### 5.1 Jerarquía de Entidades

```
Tenant (workspace)
  └── Company (empresa dentro del tenant)
        └── Branch (sucursal / sede)
              ├── User (miembro del equipo)
              ├── Lead (contacto / paciente)
              │     ├── Activity (notas, llamadas, whatsapp)
              │     ├── Conversation (conversación WA)
              │     │     └── Message
              │     ├── Scoring (historial de score)
              │     └── Tag (muchos-a-muchos)
              └── PipelineStage (etapas del funnel)
```

### 5.2 Modelo `Tenant`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK | Identificador único |
| `name` | String(255) | Nombre del workspace |
| `email` | String(255) unique | Email del owner |
| `plan` | Enum | `starter / growth / business / enterprise` |
| `is_active` | Boolean | Estado del workspace |
| `industry_key` | String(50) | Template aplicado: `salud`, `educacion`, etc. |
| `industry_label` | String(100) | Label legible del template |
| `entity_name` | String(50) | "Paciente" / "Alumno" / "Contacto" |
| `entity_plural` | String(50) | "Pacientes" / "Alumnos" / "Contactos" |
| `contact_statuses_config` | JSONB | `[{key, label, color}]` del template |
| `onboarding_description` | Text | Descripción libre del negocio |
| `onboarding_completed_at` | DateTime | Fecha de activación del template |

### 5.3 Modelo `User`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `branch_id` | UUID FK nullable | Null = acceso a todas las sucursales |
| `email` | String(255) unique | |
| `hashed_password` | String(255) | bcrypt |
| `name` | String(255) | |
| `role` | Enum | `owner / gerente / asesor / doctor / soporte / it / platform_owner` |
| `wa_phone` | String(32) | Teléfono WA del usuario |
| `is_active` | Boolean | |

### 5.4 Modelo `Lead` (entidad central del CRM)

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK | |
| `branch_id` / `tenant_id` | UUID FK | |
| `wa_phone` | String(32) nullable | Teléfono WhatsApp |
| `name` / `last_name` | String | Nombre del lead |
| `company` | String(200) | Empresa |
| `status` | Enum | `nuevo / en_calificacion / calificado / escalado / perdido` |
| `sentiment` | Enum | `neutral / interesado / urgente / negativo` |
| `source` | Enum | `whatsapp_inbound / meta_ads / manual` |
| `prospection_source` | String | Sub-fuente (campaña, formulario, etc.) |
| `assigned_to` | UUID FK nullable | Usuario asignado |
| `pipeline_stage_id` | UUID FK nullable | Etapa actual |
| `qualification_data` | JSONB | Respuestas del bot de calificación |
| `qualification_score` | Float | Score 0-100 de calificación |
| `qualification_notes` | Text | Resumen del bot |
| `current_score` | SmallInt | Score actual (0-100) |
| `current_score_trend` | String(4) | `↑ ↓ →` tendencia |
| `risk_score` | Float | Score de riesgo de churn |
| `handoff_at` / `handoff_by` | DateTime / UUID | Registro del traspaso a humano |
| `meta_lead_id` / `meta_form_id` / `meta_ad_id` | String | Datos de origen Meta Ads |
| `last_rag_context` | JSONB | Último contexto RAG inyectado al bot |
| `last_activity_summary` | Text | Resumen de última actividad |
| `deleted_at` | DateTime | Soft delete |

### 5.5 Modelo `PipelineStage`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK | |
| `branch_id` / `tenant_id` | UUID FK | |
| `name` | String(100) | Label visible |
| `slug` | String(60) | Identificador semántico (unique por branch) |
| `stage_key` | String(60) | Clave del template (e.g. `appointment`) |
| `order_index` | Integer | Posición en el pipeline |
| `color` | String(7) | Hex color `#RRGGBB` |
| `is_won` | Boolean | Etapa de cierre exitoso |
| `is_lost` | Boolean | Etapa de cierre fallido |
| `is_active` / `is_archived` | Boolean | Estado |
| `auto_advance_criteria` | Text | Criterio para avance automático |

### 5.6 Otros Modelos Relevantes

| Modelo | Descripción |
|---|---|
| `Activity` | Notas, llamadas, emails, WhatsApp, tareas por lead |
| `Conversation` | Sesión de conversación WA (status: active/handoff/closed) |
| `Message` | Mensaje individual (role: user/assistant/system) |
| `Scoring` | Historial de scores con factores positivos/negativos |
| `SavedView` | Vista guardada de filtros por usuario |
| `Tag` | Etiqueta (many-to-many con Lead) |
| `AgentSuggestion` | Sugerencia generada por un agente (status: suggested/accepted/confirmed/executed/failed) |
| `Knowledge` | Fragmento de KB con embedding pgvector |
| `MetaAds` | Configuración de integración Meta Ads por sucursal |
| `SupportSession` | Sesión temporal de soporte técnico |

---

## 6. API Reference

### Auth

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/auth/login` | `{email, password}` → `{access_token, user}` |
| POST | `/api/auth/register` | `{name, email, password}` → `{access_token, user}` |
| GET | `/api/auth/me` | → `{user: UserMeOut, tenant: TenantOut}` |

**Autenticación:** Bearer JWT en header `Authorization`. El token incluye `sub` (user_id) y `tenant_id`.

### Contacts (v1)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/v1/contacts` | Lista con filtros: `status`, `source`, `tag`, `assigned`, `search`, `dateFrom`, `dateTo`, `sort`, `order`, `page`, `limit` |
| POST | `/api/v1/contacts` | Crear contacto |
| GET | `/api/v1/contacts/:id` | Detalle del contacto |
| PATCH | `/api/v1/contacts/:id` | Actualización parcial |
| DELETE | `/api/v1/contacts/:id` | Soft delete |
| POST | `/api/v1/contacts/bulk` | Operaciones masivas (delete, tag, status) |
| POST | `/api/v1/contacts/import` | Importar CSV — retorna `job_id` (202 Accepted) |
| GET | `/api/v1/contacts/import/:job_id` | Estado del job de importación |
| GET | `/api/v1/contacts/export` | Exportar CSV |

### Vistas Guardadas

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/v1/contacts/views` | Lista de vistas del usuario |
| POST | `/api/v1/contacts/views` | Crear vista `{name, filters, is_default}` |
| PATCH | `/api/v1/contacts/views/:id` | Actualizar nombre/filtros |
| DELETE | `/api/v1/contacts/views/:id` | Eliminar vista |
| POST | `/api/v1/contacts/views/:id/set-default` | Marcar como default |

### Leads (legacy)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/leads` | Lista con filtros |
| GET | `/api/leads/:id` | Detalle |
| GET | `/api/leads/:id/conversation` | Historial de mensajes WA |
| POST | `/api/leads/:id/messages` | Enviar mensaje WA |
| POST | `/api/leads/:id/handoff` | Traspasar a humano |
| POST | `/api/leads/:id/return-to-bot` | Devolver al bot |
| PATCH | `/api/leads/:id/stage` | Mover etapa de pipeline |
| GET | `/api/leads/:id/score` | Score actual + historial |
| POST | `/api/leads/:id/score/recalculate` | Recalcular score |
| POST | `/api/leads/:id/assign` | Asignar usuario |

### Pipeline

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/pipeline/board` | Board Kanban `{stages: [{...leads}]}` |

### Dashboard y Métricas

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/dashboard` | Métricas según rol (asesor/gerente/owner/it) |
| GET | `/api/metrics/dashboard` | KPIs detallados con comparativa |
| GET | `/api/metrics/sentiment` | Análisis de sentimiento por periodo |
| GET | `/api/metrics/forecast` | Forecast de ventas y leads en riesgo |

### AI

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/ai/command` | AI Bar: ejecuta comando en lenguaje natural |
| GET | `/api/ai/context-insight` | Análisis contextual de la pantalla actual |

### Onboarding (Industry Templates — Sprint 8B)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/onboarding/analyze` | Analiza descripción del negocio (multi-turno) |
| POST | `/api/v1/onboarding/confirm` | Aplica template seleccionado |
| GET | `/api/v1/onboarding/prompt-guide` | Guía de preguntas para el wizard |

### Platform (administración)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/platform/stats` | Métricas globales: tenants, MRR, AI cost |
| GET | `/api/platform/tenants` | Lista de todos los tenants |
| POST | `/api/platform/impersonate/:id` | Token de impersonación (read-only) |

---

## 7. Sistema de IA

### 7.1 Bot Engine (WhatsApp)

El bot responde mensajes entrantes de WhatsApp de forma conversacional, calificando al lead según el template de la industria.

**Flujo:**
1. Meta → `POST /api/webhooks/whatsapp`
2. HMAC-SHA256 validation con `META_APP_SECRET`
3. `BotEngine.handle_message()`:
   - Carga contexto RAG del Knowledge Base (`rag.py`)
   - Construye prompt con historial + contexto + qualification_data actual
   - Llama Claude Haiku
   - Actualiza `qualification_data`, `qualification_score`, `sentiment`
   - Envía respuesta via `WhatsAppService.send_message()`
4. Handoff automático si `qualification_score >= threshold`

**Modelo:** `claude-haiku-4-5-20251001`

### 7.2 AI Bar (⌘K)

Interfaz de lenguaje natural para ejecutar acciones CRM desde cualquier pantalla.

**Intent types reconocidos:**
- `navigate` — abrir una sección
- `search_contacts` — buscar contactos por nombre/empresa/teléfono
- `create_contact` — crear un nuevo contacto
- `update_contact` — actualizar campos de un contacto existente
- `log_activity` — registrar nota o actividad
- `show_info` — responder preguntas sobre el CRM

**Flujo:**
```
User input → POST /api/ai/command
  → CommandInterpreter (Claude Haiku)
    → identifica intent + extrae parámetros
  → ContactExecutor (si aplica)
    → ejecuta acción en DB
  → AICommandResponse { intent_type, response_text, action_data, actions_taken }
```

### 7.3 Industry Inference

Servicio que analiza una descripción libre del negocio para inferir el `industry_key` apropiado.

**Algoritmo:**
1. **Keyword match rápido:** compara tokens con `keywords[]` de cada template
2. Si confianza ≥ 0.85 → retorna resultado directo
3. Si confianza < 0.85 → llama Claude Haiku para análisis semántico
4. Si `needs_more_info=True` → pregunta de seguimiento al usuario (multi-turno)

**Salida:** `{industry_key, confidence, extracted_data, reasoning, follow_up_questions}`

### 7.4 RAG (Retrieval-Augmented Generation)

Base de conocimiento vectorial para que el bot responda preguntas específicas del negocio (servicios, precios, horarios, etc.).

**Stack:**
- Embeddings: OpenAI `text-embedding-3-small` (ingestion)
- Vector store: `pgvector` en PostgreSQL
- Tabla: `knowledge` con columna `embedding vector(1536)`
- Retrieval: top-K por similitud coseno, filtrado por `tenant_id`

**Indexación:**
```bash
cd backend && .venv/bin/python scripts/ingest_kb.py
```

### 7.5 Observabilidad (Langfuse)

Todos los calls LLM son trazados en Langfuse con:
- `trace_id` por conversación
- `span` por llamada con input/output/latencia/tokens
- Tags por tenant, industry, modelo

---

## 8. Industry Templates

### 8.1 Concepto

Un Industry Template es un conjunto de configuraciones semánticas que personaliza todo el CRM para un giro de negocio específico. Se aplica una vez durante el onboarding del tenant.

**Campos que configura:**

| Campo | Dónde se guarda | Cómo se usa |
|---|---|---|
| `entity_name` | `Tenant.entity_name` | Label singular: "Paciente" |
| `entity_plural` | `Tenant.entity_plural` | Label plural: "Pacientes" |
| `contact_statuses` | `Tenant.contact_statuses_config` (JSONB) | Filtros, badges, colores |
| `pipeline_stages` | `PipelineStage` (rows en DB) | Etapas del Kanban |
| `industry_key` | `Tenant.industry_key` | Referencia al template activo |

### 8.2 Catálogo de Templates

| Key | Label | Entidad | Etapas | Statuses |
|---|---|---|---|---|
| `salud` | Clínica / Consultorio | Paciente/s | 7 (nuevo→alta/perdido) | Nuevo, Activo, En pausa, Inactivo |
| `bienes_raices` | Bienes Raíces | Prospecto/s | 8 (interesado→cerrado/perdido) | Nuevo, Activo, Cliente, Inactivo |
| `educacion` | Escuela / Academia | Alumno/s | 8 (interesado→egresado/baja) | Nuevo, Activo, Alumni, Inactivo |
| `estetica_wellness` | Estética / Wellness | Cliente/s | 7 (nuevo→reactivar/perdido) | Nuevo, Activo, VIP, Inactivo |
| `automotriz` | Agencia Automotriz | Cliente/s | 8 (nuevo→entregado/perdido) | Nuevo, Activo, VIP, Inactivo |
| `restaurante` | Restaurante / Foodservice | Cliente/s | 7 (nuevo→reactivar/perdido) | Nuevo, Activo, VIP, Inactivo |
| `servicios_profesionales` | Servicios Profesionales | Cliente/s | 7 (nuevo→renovación/perdido) | Nuevo, Activo, En pausa, Inactivo |
| `generico` | Genérico (default) | Contacto/s | 6 (nuevo→cerrado/perdido) | Nuevo, Activo, Inactivo |

### 8.3 Flujo de Aplicación de Template

```
POST /api/v1/onboarding/confirm { industry_key, description }
  └── TenantSetupService.apply_template(tenant_id, industry_key)
        1. get_template(industry_key)              ← catalog.py
        2. tenant.industry_key = industry_key
           tenant.entity_name = template.entity_name
           tenant.entity_plural = template.entity_plural
           tenant.contact_statuses_config = template.contact_statuses
        3. PipelineStage.is_archived = True         ← archivar stages anteriores
           (renombra slug para liberar constraint único)
        4. PipelineStage.create_from_template()     ← crea nuevas etapas
        5. db.commit()
```

### 8.4 Detección Automática

Durante el onboarding wizard (`OnboardingWizard.tsx`), el usuario describe su negocio en lenguaje natural. El sistema llama:

```
POST /api/v1/onboarding/analyze { description, session_id? }
  ← { needs_more_info, industry_key, confidence, pipeline_preview, follow_up_questions }
```

Si `needs_more_info=true`, se muestra la `follow_up_question` y el usuario responde. Máximo 3 turnos antes de mostrar selector manual.

---

## 9. Multi-tenancy y Seguridad

### 9.1 Modelo de Aislamiento

**Tres capas de aislamiento:**

1. **Aplicación:** Todo query filtra explícitamente por `tenant_id` en los endpoints
2. **Middleware:** `TenantContextMiddleware` inyecta `tenant_id` en el contexto de la sesión de PostgreSQL
3. **Base de datos:** Políticas de Row-Level Security (RLS) en todas las tablas con `tenant_id`

```sql
-- Ejemplo de política RLS
CREATE POLICY tenant_isolation ON leads
  USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

### 9.2 JWT Auth

- Signing: HMAC-SHA256 con `SECRET_KEY`
- Payload: `{ sub: user_id, tenant_id, exp }`
- Storage: `localStorage` key `walix_token`
- Refresh: no implementado (token de larga duración)

### 9.3 Roles de Usuario

| Rol | Acceso |
|---|---|
| `platform_owner` | Dashboard global, lista de tenants, impersonación |
| `owner` | Todo el tenant: todas las sucursales, configuración, equipo |
| `gerente` | Una sucursal: reportes, pipeline, equipo de esa sucursal |
| `asesor` | Sus propios leads asignados |
| `doctor` | Vista médica (específico de salud) |
| `it` | Configuración técnica: webhook, Meta Ads, KB |
| `soporte` | Sesión temporal de soporte técnico |

### 9.4 Impersonación (Platform Owner)

El `platform_owner` puede obtener un token de impersonación `read_only_impersonation=true` para cualquier tenant. La UI muestra un banner de aviso y restringe acciones destructivas.

### 9.5 CORS

Permitido: `FRONTEND_URL` (por defecto `http://localhost:3000`) y `https://walix*.vercel.app` (regex). Configurado en `main.py` con `CORSMiddleware`.

---

## 10. Configuración e Infraestructura

### 10.1 Variables de Entorno (Backend)

```bash
# Obligatorias
DATABASE_URL=postgresql+asyncpg://...
SECRET_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
META_VERIFY_TOKEN=...
META_APP_SECRET=...
REDIS_URL=redis://...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...

# Opcionales
DATABASE_PUBLIC_URL=...          # Railway proxy para desarrollo local
APP_ENV=development              # development | production
FRONTEND_URL=http://localhost:3000
OPENAI_API_KEY=...               # Solo para scripts/ingest_kb.py
WALIX_INTERNAL_WA_NUMBER_ID=... # Línea interna de staff Walix
WALIX_INTERNAL_WA_TOKEN=...
LANGFUSE_HOST=https://us.cloud.langfuse.com
```

### 10.2 Variables de Entorno (Frontend)

```bash
VITE_API_URL=http://localhost:8000   # URL del backend
```

### 10.3 Servicios Externos

| Servicio | Uso | Provider |
|---|---|---|
| PostgreSQL 16 | Base de datos principal + pgvector | Railway |
| Redis | Cache, colas de tareas | Upstash |
| Meta WhatsApp Business API | Canal de mensajería | Meta |
| Anthropic Claude | LLM (bot, AI Bar, onboarding) | Anthropic |
| OpenAI | Embeddings para RAG | OpenAI |
| Langfuse | Observabilidad de LLM traces | Langfuse Cloud |
| Railway | Deploy backend | Railway |
| Vercel | Deploy frontend | Vercel |

### 10.4 CI/CD

```
git push main
  ├── GitHub Actions: tests pytest + ESLint + TypeScript
  ├── Railway: auto-deploy backend (docker build)
  └── Vercel: auto-deploy frontend (vite build)
```

---

## 11. Desarrollo Local

### 11.1 Requisitos

- Python 3.13+
- Node 22+
- PostgreSQL 16 con extensión pgvector
- Redis

### 11.2 Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Crear .env con las variables necesarias
cp .env.example .env   # editar con credenciales

# Migraciones
.venv/bin/alembic upgrade head

# Datos de prueba
.venv/bin/python scripts/seed.py          # tenant clínica beta
.venv/bin/python scripts/add_test_users.py  # usuarios adicionales

# Servidor
.venv/bin/uvicorn app.main:app --reload --port 8000
```

**Usuarios de prueba (password: `walix2026`):**

| Email | Rol | Tenant |
|---|---|---|
| `admin@clinica.com` | owner | Clínica beta |
| `asistente@clinica.com` | asesor | Clínica beta |
| `doctor@clinica.com` | doctor | Clínica beta |
| `test3@mail.com` | owner | Test3 (industry: salud) |

### 11.3 Frontend

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

### 11.4 Scripts de Verificación

```bash
# Verificar nomenclatura dinámica en BD
cd backend && .venv/bin/python scripts/test_nomenclatura.py

# Test Sprint 8B (Industry Templates)
.venv/bin/python scripts/test_sprint8b.py

# Simular webhook WhatsApp entrante
.venv/bin/python scripts/test_webhook.py

# Test de handoff bot → humano
.venv/bin/python scripts/test_handoff.py

# Backfill de métricas históricas
.venv/bin/python scripts/backfill_metrics.py
```

---

## 12. Historial de Sprints

| Sprint | Funcionalidades principales |
|---|---|
| **Sprint 1** | Bot WhatsApp básico, webhook Meta, modelo Lead, calificación inicial |
| **Sprint 3** | Multi-tenancy, Branch/Company model, RLS, roles de usuario |
| **Sprint 4** | Pipeline Kanban, PipelineStage model, board endpoint |
| **Sprint 5** | Dashboard role-aware, métricas KPI, sentiment analysis |
| **Sprint 6** | Agentes autónomos, AI Bar (⌘K), RAG Knowledge Base, forecast |
| **Sprint 7** | Módulo Contactos (CRUD, vistas lista/kanban/cards, import/export CSV) |
| **Sprint 8A** | Vistas guardadas (SavedView), mejoras AI Bar CRUD |
| **Sprint 8B** | Industry Templates: catálogo, IndustryInference, TenantSetup, OnboardingWizard, nomenclatura dinámica en UI |

---

*Documento generado: Junio 2026 · Walix CRM*
