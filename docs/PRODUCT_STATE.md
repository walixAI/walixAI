# Walix — Estado del Producto · Sprint 13A

**Fecha:** Julio 2026  
**Branch:** main · Producción activa  
**Versión:** 1.0-rc (Release Candidate)

---

## Qué es Walix

Walix es un **CRM conversacional sobre WhatsApp** para PyMEs mexicanas. Captura leads que llegan por WhatsApp Business o Meta Ads, los califica automáticamente con IA, los mueve por un pipeline de ventas, y genera sugerencias proactivas para que el equipo de ventas cierre más.

**Propuesta de valor central:**  
El bot de WhatsApp hace la primera calificación 24/7. Cuando el lead está listo, lo pasa a un asesor humano con todo el contexto. Los agentes de IA corren en background y avisan al equipo qué hacer a continuación.

---

## Qué se ha construido (inventario completo)

### Módulo 1 — Captura y calificación de leads

| Funcionalidad | Estado | Descripción |
|--------------|--------|-------------|
| Webhook Meta WhatsApp | ✅ Producción | Recibe mensajes inbound; deduplicación 24h por `wa_message_id` |
| Bot conversacional (Claude Haiku) | ✅ Producción | Responde, califica y escala leads vía WhatsApp |
| Calificación automática | ✅ Producción | Score 0–100 basado en respuestas + historial |
| Handoff bot → asesor | ✅ Producción | Detecta frases de escalación; notifica al equipo |
| Return to bot | ✅ Producción | Asesor devuelve lead al bot después de atender |
| Meta Lead Ads integration | ✅ Producción | Leads desde formularios de Facebook/Instagram entran directo al CRM |
| Asignación de leads | ✅ Producción | Automática (equitativa/pool) o manual por gerente |
| RAG con Knowledge Base | ✅ Producción | El bot usa documentos del tenant para responder preguntas específicas |

---

### Módulo 2 — CRM de contactos

| Funcionalidad | Estado | Descripción |
|--------------|--------|-------------|
| CRUD leads completo | ✅ Producción | Crear, editar, eliminar (soft-delete), filtrar, buscar |
| Campos de lead | ✅ Producción | Nombre, apellido, empresa, teléfono WA, status, sentimiento, score, stage, asignado a |
| Status del lead | ✅ Producción | nuevo → en_calificacion → calificado → escalado → perdido |
| Sentimiento | ✅ Producción | neutral / interesado / urgente / negativo |
| Etiquetas (Tags) | ✅ Producción | Custom por tenant, M2M con leads, color picker |
| Historial de conversación | ✅ Producción | Chat WhatsApp completo en el CRM |
| Timeline de actividades | ✅ Producción | Notes, calls, meetings, emails, tasks + system events |
| Búsqueda y filtros | ✅ Producción | Por nombre, status, stage, etiqueta, asesor, fechas |
| Import CSV | ✅ Producción | Hasta 1,000 leads por batch |
| Export CSV | ✅ Producción | Todos los leads del branch con filtros aplicados |
| Bulk actions | ✅ Producción | Asignación masiva, cambio de status masivo |
| Vistas guardadas | ✅ Producción | Filtros custom persistentes por usuario |
| Asignación por sucursal | ✅ Producción | Leads asignados a usuarios del branch correcto |

---

### Módulo 3 — Pipeline de ventas

| Funcionalidad | Estado | Descripción |
|--------------|--------|-------------|
| Pipeline stages custom | ✅ Producción | Etapas configurables por branch (nombre, color, orden, probabilidad) |
| Kanban board | ✅ Producción | Drag & drop; columnas configurables |
| Oportunidades | ✅ Producción | Monto, probabilidad, fecha de cierre, título |
| Deals (modelo alternativo) | ✅ Producción | CRUD completo; historial de movimientos entre etapas |
| Lead health badges | ✅ Producción | Stale / Hot / At-risk (basado en tiempo sin actividad) |
| Marcar won/lost | ✅ Producción | Con captura de razón de pérdida |
| Stage history | ✅ Producción | Auditoría completa de movimientos por etapa |
| Forecast | ✅ Producción | Proyección de revenue ponderada por probabilidad |
| Vista lista alternativa | ✅ Producción | Table view como alternativa a Kanban |
| Filtros avanzados pipeline | ✅ Producción | Por owner, stage, monto, probabilidad, fecha |
| Export oportunidades CSV | ✅ Producción | Con filtros aplicados |

---

### Módulo 4 — Dashboard y métricas

| Funcionalidad | Estado | Descripción |
|--------------|--------|-------------|
| Dashboard role-basado | ✅ Producción | Vista diferente para asesor / gerente / owner / IT / platform_owner |
| KPIs diarios | ✅ Producción | Leads creados, calificados, ganados, perdidos, mensajes enviados/recibidos |
| Métricas por asesor | ✅ Producción | Breakdown individual de performance |
| Sentimiento agregado | ✅ Producción | Score general + distribución + por etapa + por asesor |
| Pipeline health | ✅ Producción | % leads por etapa, tiempo promedio en etapa |
| ROI Dashboard | ✅ Producción | Revenue por conversión, costo por lead, ROI general |
| Forecast page | ✅ Producción | Revenue proyectado por período con filtros |
| Platform Dashboard | ✅ Producción | Vista global para platform_owner (admin de Walix) |

---

### Módulo 5 — Agentes de IA

| Agente | Estado | Descripción |
|--------|--------|-------------|
| Follow-up Agent | ✅ Producción | Re-engagement de leads inactivos >24h |
| Pipeline Agent | ✅ Producción | Detecta bottlenecks diarios en el pipeline |
| Closing Agent | ✅ Producción | Propuestas de cierre para leads con score ≥70 |
| Config Agent | ✅ Producción | Recomendaciones semanales de configuración de pipeline |
| Reactivation Agent | ✅ Producción | Reactiva leads perdidos >30 días |
| Profile Enrichment Agent | ✅ Producción | Sugiere completar datos faltantes de leads |
| Sugerencias aceptar/rechazar | ✅ Producción | UI para que asesor/gerente actúe sobre sugerencias |
| Executor de sugerencias | ✅ Producción | Ejecuta la acción aprobada (mensaje, cambio de status, etc.) |

---

### Módulo 6 — Knowledge Base

| Funcionalidad | Estado | Descripción |
|--------------|--------|-------------|
| Upload documentos | ✅ Producción | PDF, DOCX, TXT |
| Chunking e indexación | ✅ Producción | Split automático + embeddings pgvector |
| RAG retrieval | ✅ Producción | Cosine similarity; contexto inyectado en prompts del bot |
| Gestión documentos | ✅ Producción | Listar, ver, eliminar |
| Auto-generated docs | ✅ Producción | Documentos generados desde onboarding |

---

### Módulo 7 — Onboarding e industrias

| Funcionalidad | Estado | Descripción |
|--------------|--------|-------------|
| Onboarding wizard | ✅ Producción | 4-step: negocio, pipeline, bot, configuración |
| Templates por industria | ✅ Producción | Clínica médica, agencia inmobiliaria, escuela, restaurante, etc. |
| Bot config auto-generada | ✅ Producción | System prompt + tono + preguntas de calificación desde onboarding |
| Preview pre-aprobación | ✅ Producción | Owner aprueba configuración antes de activar |
| Industry inference | ✅ Producción | Inferencia automática de industria desde descripción |
| Entity names custom | ✅ Producción | "Paciente" vs "Alumno" vs "Cliente" según industria |
| Contact statuses custom | ✅ Producción | Estados del CRM adaptados por industria |

---

### Módulo 8 — Multi-tenant y equipos

| Funcionalidad | Estado | Descripción |
|--------------|--------|-------------|
| Multi-tenancy completo | ✅ Producción | Row-level security por tenant_id en todas las tablas |
| Sucursales múltiples | ✅ Producción | Cada branch tiene su propio bot, pipeline y equipo |
| Roles granulares | ✅ Producción | owner, gerente, asesor, doctor, soporte, IT, platform_owner |
| Gestión de equipo | ✅ Producción | Invitar, editar, desactivar usuarios |
| Soporte técnico con código | ✅ Producción | Sesiones de soporte con access_code temporal (read-only) |
| Trial guard | ✅ Producción | Bloquea APIs si trial expiró sin suscripción activa |

---

### Módulo 9 — Billing (Stripe)

| Funcionalidad | Estado | Descripción |
|--------------|--------|-------------|
| Planes de suscripción | ✅ Producción | Starter / Growth / Business / Enterprise |
| Trial 14 días | ✅ Producción | Automático en registro; bloqueo suave al expirar |
| Checkout Session | ✅ Producción | Flujo de pago via Stripe |
| Customer Portal | ✅ Producción | Gestión de suscripción directa en Stripe |
| Webhook Stripe | ✅ Producción | invoice.payment_failed, customer.subscription.updated/deleted |
| Tracking de pagos fallidos | ✅ Producción | Log en DB; notificación al owner |
| Cancelación / Reactivación | ✅ Producción | Via API o Stripe Portal |

---

### Módulo 10 — Configuración y settings

| Funcionalidad | Estado | Descripción |
|--------------|--------|-------------|
| Settings página | ✅ Producción | Tabs: Perfil, Bot, Pipeline, Alertas, KB, Team |
| Config de bot por branch | ✅ Producción | System prompt, tono, preguntas de calificación |
| Alertas configurables | ✅ Producción | Threshold de horas, horario de silencio |
| WhatsApp token y phone ID | ✅ Producción | Configurado por branch |
| Assignment mode | ✅ Producción | Equitativa (round-robin) o pool (cualquier asesor) |

---

## Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────┐
│                     FRONTEND (React/Vite)                │
│           Vite 5.4 · TypeScript · Tailwind · Shadcn      │
│           TanStack Query · Zustand · Recharts            │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP/REST
┌─────────────────────▼───────────────────────────────────┐
│                    BACKEND (FastAPI)                      │
│              Python 3.13 · SQLAlchemy 2.0                │
│         26 routers · JWT auth · Trial guard              │
│              Multi-tenant middleware                     │
└──────┬──────────────┬───────────────┬───────────────────┘
       │              │               │
┌──────▼──────┐ ┌─────▼──────┐ ┌─────▼──────────────────┐
│  PostgreSQL  │ │   Redis    │ │    Celery + Beat        │
│  +pgvector  │ │  (Upstash) │ │  12 scheduled tasks     │
│  33 tablas  │ │  broker +  │ │  6 agentes IA           │
│  UUID PKs   │ │  dedup     │ │  metrics + alerts       │
└─────────────┘ └────────────┘ └────────────┬───────────┘
                                             │
┌────────────────────────────────────────────▼───────────┐
│               INTEGRACIONES EXTERNAS                    │
│  Meta WA Graph API · Anthropic Claude Haiku             │
│  Stripe · Langfuse · OpenAI (KB ingest, opcional)       │
└─────────────────────────────────────────────────────────┘
```

---

## Números del producto

| Dimensión | Cantidad |
|-----------|---------|
| Modelos de base de datos | 33 |
| Endpoints API (routers) | 26 módulos, ~90 endpoints |
| Páginas frontend | 22 |
| Componentes UI | 128 |
| Agentes de IA proactivos | 6 |
| Tareas Celery programadas | 12 |
| Sprints completados | 13 (Sprint 13A) |
| Migraciones Alembic | 30+ |
| Templates de industria | 8+ |
| Roles de usuario | 7 |

---

## Planes y precios

| Plan | Incluye |
|------|---------|
| **Trial (14 días)** | Funcionalidades completas; sin tarjeta |
| **Starter** | 1 sucursal, hasta 5 usuarios, 1,000 leads/mes |
| **Growth** | 3 sucursales, hasta 15 usuarios, agentes IA incluidos |
| **Business** | 10 sucursales, usuarios ilimitados, ROI Dashboard |
| **Enterprise** | Sin límites, SLA, soporte dedicado |

---

## Lo que NO está construido (pendiente)

- Notificaciones push / email al asesor en handoff
- App móvil nativa
- Integraciones con CRMs externos (HubSpot, Salesforce)
- Configuración de pipeline stages desde la UI (actualmente via DB/onboarding)
- Reportes descargables en PDF
- Multi-idioma (actualmente solo español)
- Automations page funcional (existe página placeholder)
