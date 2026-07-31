# Walix — Automatizaciones y Agentes de IA

**Versión:** Sprint 13A · Julio 2026  
**Modelo IA:** Claude Haiku (`claude-haiku-4-5-20251001`)  
**Observabilidad:** Langfuse (tracing completo)

---

## Visión general

Walix tiene dos capas de automatización:

1. **Bot conversacional** — responde leads en tiempo real vía WhatsApp
2. **6 agentes proactivos** — corren en background en horarios programados y generan sugerencias para el equipo

Las automatizaciones están orquestadas por **Celery + Beat** con Redis como broker.

---

## Bot Conversacional (WhatsApp)

### Flujo completo

```
Cliente escribe en WhatsApp
        │
        ▼
Meta Graph API → Webhook POST /api/webhooks/meta
        │
        ▼
[Deduplicación Redis: 24h por wa_message_id]
        │
        ▼
Buscar / crear Lead + Conversation en DB
        │
        ▼
¿Conversación en modo bot? ──No──→ Descartar (atiende humano)
        │ Sí
        ▼
RAG Retrieval: buscar chunks KB relevantes (pgvector cosine)
        │
        ▼
Construir prompt:
  - System prompt del branch (configurado en Settings)
  - Perfil del lead (nombre, empresa, historial)
  - Últimos 8 mensajes de la conversación
  - Contexto RAG (si KB tiene documentos)
        │
        ▼
Claude Haiku → respuesta (max 300 tokens)
        │
        ▼
¿Detecta frase de escalación?
  ("quiero hablar con alguien", "cuánto cuesta", etc.)
  │ Sí                    │ No
  ▼                       ▼
Handoff:              Enviar respuesta
- Status → escalado     por WhatsApp Graph API
- Notificar equipo      Guardar Message en DB
- current_handler       Actualizar conversation_history
  = human               en Redis (TTL 24h)
```

### Detección de escalación
El bot detecta automáticamente cuando debe pasar a un humano. Frases que triggean handoff:
- Solicitudes de precio / cotización
- Solicitudes de hablar con asesor/vendedor/doctor
- Quejas o insatisfacción
- Preguntas muy específicas fuera del KB
- Cualquier frase en `escalation_phrases` del bot config

### Calificación de leads
El bot asigna un **score de calificación 0–100** basado en:
- Respuestas a las preguntas de calificación
- Sentimiento detectado en la conversación
- Urgencia expresada por el cliente
- Completitud del perfil (datos proporcionados)

El score actualiza el campo `qualification_score` del lead en tiempo real.

### Gestión de la conversación
| Estado | Descripción |
|--------|-------------|
| `bot` | El bot está respondiendo automáticamente |
| `human` | Un asesor está atendiendo manualmente |
| `closed` | Conversación cerrada |

El asesor puede devolver el lead al bot desde el CRM → `POST /leads/{id}/return-to-bot`

---

## 6 Agentes Proactivos de IA

Los agentes corren en Celery Beat y crean `AgentSuggestion` en la DB. El equipo ve las sugerencias en el dashboard y decide qué hacer.

### Estructura de una sugerencia

```json
{
  "agent_type": "follow_up",
  "suggestion_text": "El lead Juan García lleva 26h sin respuesta...",
  "action_payload": {
    "action": "send_whatsapp_message",
    "lead_id": "uuid",
    "message": "Hola Juan, ¿pudiste revisar la información que te enviamos?"
  },
  "target_user_id": "uuid-asesor",
  "status": "suggested",
  "expires_at": "2026-07-11T09:00:00Z"
}
```

### Estados de una sugerencia

```
suggested → accepted → executed
         ↘ dismissed
         ↘ expired (automático por expires_at)
```

---

### Agente 1: Follow-up Agent

**Archivo:** `app/agents/follow_up_agent.py`  
**Trigger:** Cada 2 horas (08:00–20:00)  
**Task Celery:** `run_follow_up_all_branches`

**Lógica:**
1. Busca leads con conversación bot activa donde el último mensaje fue hace >24h
2. Recupera historial de los últimos mensajes
3. Claude genera un mensaje de re-engagement personalizado para ese lead
4. Crea `AgentSuggestion` dirigida al asesor asignado

**Deduplicación:** No genera otra sugerencia para el mismo lead si ya hay una activa <6h

**Ejemplo de output:**
```
Sugerencia: "Juanita López no ha respondido en 27 horas. 
Su última pregunta fue sobre precios de planes.
Mensaje sugerido: 'Hola Juanita 😊 Te recuerdo que tenemos disponibilidad 
esta semana. ¿Te gustaría agendar una llamada de 15 minutos?'"
```

---

### Agente 2: Pipeline Agent

**Archivo:** `app/agents/pipeline_agent.py`  
**Trigger:** Diariamente a las 07:00  
**Task Celery:** `run_pipeline_all_branches`

**Lógica:**
1. Analiza distribución de leads por etapa del pipeline
2. Detecta leads `stalled` (>7 días sin cambio de etapa)
3. Identifica cuellos de botella (etapa con >40% del total)
4. Claude genera recomendación de acción para el gerente

**Ejemplo de output:**
```
Sugerencia: "Tienes 8 leads en 'Propuesta enviada' sin actividad en más de 
7 días. 5 de ellos llevan más de 2 semanas sin respuesta.
Acción recomendada: Llama a los 3 con mayor score esta semana 
(Carlos R., Ana M., Pedro L.)"
```

---

### Agente 3: Closing Agent

**Archivo:** `app/agents/closing_agent.py`  
**Trigger:** Diariamente a las 09:00  
**Task Celery:** `run_closing_all_branches`

**Lógica:**
1. Busca leads con `qualification_score ≥ 70`
2. Que tengan actividad reciente (<48h)
3. Claude genera propuesta de cierre personalizada basada en el perfil

**Ejemplo de output:**
```
Sugerencia: "María González tiene score 84/100 y está muy interesada.
Lleva 3 días en negociación.
Mensaje de cierre sugerido: 'María, ¿qué necesitas para tomar la decisión 
esta semana? Podemos ofrecerte el plan Business con 2 meses de cortesía.'"
```

---

### Agente 4: Config Agent

**Archivo:** `app/agents/config_agent.py`  
**Trigger:** Lunes a las 08:00 (semanal)  
**Task Celery:** `run_config_all_branches`

**Lógica:**
1. Revisa configuración de etapas del pipeline
2. Analiza distribución de leads y tiempo promedio por etapa
3. Claude sugiere optimizaciones de configuración

**Ejemplo de output:**
```
Sugerencia: "Tu etapa 'Calificado' concentra el 52% de todos los leads.
Considera dividirla en 'Calificado - Frío' y 'Calificado - Caliente' 
para que tus asesores prioricen mejor."
```

---

### Agente 5: Reactivation Agent

**Archivo:** `app/agents/reactivation_agent.py`  
**Trigger:** Diariamente a las 10:00  
**Task Celery:** `run_reactivation_all_tenants`

**Lógica:**
1. Busca leads con status `perdido` y último contacto >30 días
2. Filtra los que tuvieron alto interés en algún punto (score histórico >50)
3. Claude genera mensaje de reactivación contextualizado

**Ejemplo de output:**
```
Sugerencia: "Roberto Sánchez fue marcado como perdido hace 45 días 
(razón: 'precio alto'). Tuvo score 71 en su momento.
Mensaje de reactivación: 'Hola Roberto, ¿cómo estás? Tenemos una 
promoción especial este mes que creo que te puede interesar...'"
```

---

### Agente 6: Profile Enrichment Agent

**Archivo:** `app/agents/profile_enrichment_agent.py`  
**Trigger:** Cada 72 horas  
**Task Celery:** `run_profile_enrichment_all_tenants`

**Lógica:**
1. Busca leads con campos clave vacíos (empresa, cargo, presupuesto)
2. Claude sugiere qué preguntas hacer en la siguiente interacción
3. Las preguntas son naturales y conversacionales, no un formulario

**Ejemplo de output:**
```
Sugerencia: "Ana Torres no tiene empresa ni cargo registrados.
En tu próxima conversación, pregunta naturalmente:
'Ana, ¿trabajas de manera independiente o en alguna empresa?'
Esto te ayudará a personalizar mejor tu propuesta."
```

---

## Automatizaciones de métricas y alertas

### Agregación diaria de KPIs

**Trigger:** Cada hora a los :05 minutos (para el día anterior)  
**Task:** `aggregate_all_metrics`

**Métricas calculadas por branch:**
| Métrica | Cálculo |
|---------|---------|
| `leads_created` | COUNT leads creados en el día |
| `leads_qualified` | COUNT transiciones a `calificado` |
| `leads_won` | COUNT transiciones a etapa `is_won=true` |
| `leads_lost` | COUNT transiciones a etapa `is_lost=true` |
| `messages_sent` | COUNT mensajes role=assistant en el día |
| `messages_received` | COUNT mensajes role=user en el día |
| `calls_logged` | COUNT actividades tipo `call` |
| `tasks_completed` | COUNT actividades tipo `task` con `completed_at` |
| `avg_first_response_sec` | AVG(primer mensaje bot - creación lead) |
| `metrics_by_agent` | Breakdown de leads activos por usuario asignado |

**Persistencia:** UPSERT en `daily_metrics`; una fila por (branch, fecha)

---

### Snapshot de sentimiento diario

**Trigger:** Diariamente a las 23:00  
**Task:** `calculate_all_sentiment`

**Cálculo:**
```
overall_score = (
    interesado * 1.0 + 
    urgente    * 0.9 + 
    neutral    * 0.5 + 
    negativo   * 0.0
) / total_leads
```

**Output por branch:**
```json
{
  "overall_score": 0.72,
  "distribution": {
    "neutral": 45,
    "interesado": 32,
    "urgente": 8,
    "negativo": 5
  },
  "by_stage": {
    "stage_uuid_1": 0.85,
    "stage_uuid_2": 0.60
  },
  "by_agent": {
    "user_uuid_1": 0.80,
    "user_uuid_2": 0.65
  }
}
```

---

### Alertas de leads sin respuesta

**Trigger:** Cada 30 minutos  
**Task:** `detect_unresponded_leads`

**Lógica:**
1. Por cada `AlertRule` activa (con `is_active=True`)
2. Respeta horario de silencio (no enviar entre `silence_start` y `silence_end`)
3. Busca leads activos sin respuesta de asesor en más de `threshold_hours`
4. Envía mensaje WhatsApp al número configurado del gerente

**Mensaje de alerta:**
```
⚠️ Lead sin atender

Nombre: María González
Teléfono: +52 55 1234 5678
Horas sin respuesta: 4h 23min
Última actividad: Bot calificó el lead

Ingresa al CRM para atenderlo.
```

---

### Resumen diario automatizado

**Trigger:** Cada hora (evalúa si corresponde el `schedule_hour` de cada branch)  
**Task:** `run_daily_summaries`

**Mensaje enviado por WhatsApp:**
```
📊 Resumen del día — 10 Jul 2026

Leads creados: 12
Leads calificados: 8 (67%)
Ganados hoy: 3 🎉
Perdidos: 1
Mensajes enviados: 145

Top asesor: Carlos López (5 leads calificados)

¡Buen trabajo al equipo!
```

---

### Resumen mensual

**Trigger:** Primer día del mes a las 09:00  
**Task:** `run_monthly_summaries`

**Incluye:**
- KPIs del mes vs mes anterior (variación %)
- Top 3 asesores del mes
- Leads ganados y revenue generado
- Tasa de conversión general

---

### Generación de gastos recurrentes

**Trigger:** Primer día del mes a las 06:00 (antes que el resumen mensual a las 09:00)  
**Task Celery:** `app.tasks.finance_tasks.run_generate_recurring_expenses`  
**Archivo:** `app/tasks/finance_tasks.py`

**Qué hace:**
- Itera todos los `RecurringExpense` activos de todos los tenants
- Para cada plantilla, crea un `Expense` con `source="recurring"` y `status="confirmed"` en el día del mes configurado (`day_of_month`, rango 1-28)
- Idempotente: si ya existe un `Expense` con ese `recurring_id` dentro del mes actual, lo omite (seguro si el worker cae y se re-ejecuta)
- También se puede disparar manualmente con `POST /api/finance/recurring-expenses/generate` (requiere rol OWNER)

---

## Cronograma completo de automatizaciones

```
00:00 ─────────────────────────────────────────────────────
  :00  Resumen diario (si corresponde por schedule_hour)
  :05  Agregación KPIs diarios (para el día anterior)
  :30  Detección leads sin respuesta

01:00 ─────────────────────────────────────────────────────
  :00  Resumen diario
  :05  Agregación KPIs
  :30  Detección leads sin respuesta

... (cada hora) ...

07:00 ─────────────────────────────────────────────────────
  :00  Pipeline Agent (análisis diario)

08:00 ─────────────────────────────────────────────────────
  :00  Follow-up Agent (primera ejecución del día)
  :00  Config Agent (solo lunes)

06:00 ─────────────────────────────────────────────────────
  :00  Generación gastos recurrentes (solo día 1)

09:00 ─────────────────────────────────────────────────────
  :00  Closing Agent
  :00  Resumen mensual (solo día 1)

10:00 ─────────────────────────────────────────────────────
  :00  Reactivation Agent

10:00 ─────────────────────────────────────────────────────
       Profile Enrichment Agent (cada 72h)

10:00 ─────────────────────────────────────────────────────
       Follow-up Agent (segunda ejecución)

12:00 ─────────────────────────────────────────────────────
       Follow-up Agent (tercera ejecución)

14:00 ─────────────────────────────────────────────────────
       Follow-up Agent

16:00 ─────────────────────────────────────────────────────
       Follow-up Agent

18:00 ─────────────────────────────────────────────────────
       Follow-up Agent

20:00 ─────────────────────────────────────────────────────
       Follow-up Agent (última del día)

23:00 ─────────────────────────────────────────────────────
       Snapshot de sentimiento
```

---

## Executor de sugerencias

**Archivo:** `app/agents/executor.py`  
**Endpoint:** `POST /api/agents/suggestions/{id}/confirm`

Cuando el usuario acepta una sugerencia, el Executor ejecuta la acción correspondiente:

| `action` en payload | Qué hace |
|--------------------|---------|
| `send_whatsapp_message` | Envía el mensaje exacto via WhatsApp Graph API |
| `update_lead_status` | Cambia el status del lead en DB |
| `assign_lead` | Asigna el lead a otro asesor |
| `update_pipeline_stage` | Mueve el lead a otra etapa |
| `create_activity` | Crea una nota o actividad en el timeline |

El resultado se registra en `execution_result` y `error_detail` de `AgentSuggestion`.

---

## Dead Letter Queue (DLQ)

**Archivo:** `app/tasks/dlq_handler.py`  
**Modelo:** `FailedTask`

Si una tarea Celery falla después de 3 reintentos:
1. Se guarda en la tabla `failed_tasks` con `task_name`, `error`, `retry_count`
2. Disponible para revisión en el Platform Dashboard (admin)
3. Permite re-ejecutar manualmente desde el sistema

---

## RAG (Retrieval Augmented Generation)

**Archivo:** `app/services/rag.py`  
**Modelo embeddings:** Claude API (1536 dimensiones)  
**DB:** PostgreSQL + pgvector (cosine similarity)

### Flujo de ingestión

```
Subir documento (PDF/DOCX/TXT)
        │
        ▼
Extraer texto del archivo
        │
        ▼
Dividir en chunks (~500 tokens c/u)
        │
        ▼
Generar embedding para cada chunk (Claude API)
        │
        ▼
Guardar KnowledgeChunk en PostgreSQL con vector
        │
        ▼
Actualizar KnowledgeDocument (chunk_count, indexed_at)
```

### Flujo de retrieval (durante conversación)

```
Mensaje del cliente
        │
        ▼
Generar embedding del mensaje
        │
        ▼
SELECT chunks ORDER BY embedding <-> query_embedding LIMIT 5
(cosine similarity en pgvector)
        │
        ▼
Formatear chunks como contexto
        │
        ▼
Inyectar en prompt de Claude antes del historial de mensajes
```

### Cuándo se usa RAG
- Solo si el branch tiene documentos indexados en KB
- Solo para conversaciones activas con el bot
- El contexto se incluye automáticamente; no hay configuración adicional

---

## Observabilidad de IA (Langfuse)

Todas las llamadas a Claude están instrumentadas con Langfuse:

```python
with langfuse.trace(name="bot_response", user_id=lead_id):
    response = anthropic.messages.create(...)
    langfuse.generation(
        name="claude_haiku",
        model="claude-haiku-4-5-20251001",
        input=messages,
        output=response.content,
        usage=response.usage
    )
```

**Métricas disponibles en Langfuse:**
- Latencia por llamada
- Tokens usados (input + output + costo)
- Tasa de éxito/error
- Historial de prompts y respuestas

---

## Configuración de IA por industria

El sistema incluye templates pre-construidos para distintas industrias. Estos definen:

| Template | Industria | Entidad | Estatus custom | Preguntas calificación |
|---------|-----------|---------|---------------|----------------------|
| `medical_clinic` | Clínica médica | Paciente | Interesado, Agenda, Consulta, No aplica | ¿Para quién es? ¿Tiene seguro? ¿Urgente? |
| `real_estate` | Inmobiliaria | Cliente | Buscando, Visita, Propuesta, Cerrado | ¿Compra o renta? ¿Presupuesto? ¿Zona? |
| `education` | Escuela/Instituto | Alumno | Consulta, Visita, Inscrito, Egresado | ¿Qué programa? ¿Cuándo? ¿Modalidad? |
| `restaurant` | Restaurante | Comensal | Nuevo, Regular, VIP | ¿Evento o casual? ¿Cuántos? ¿Fecha? |
| `gym_fitness` | Gym/Fitness | Miembro | Prospecto, Demo, Activo, Baja | ¿Objetivo? ¿Experiencia? ¿Horario? |
| `retail` | Retail/Ecommerce | Comprador | Interesado, Carrito, Compra, Recurrente | ¿Qué busca? ¿Presupuesto? ¿Urgente? |

El onboarding selecciona automáticamente el template según la industria del negocio, y genera:
- System prompt personalizado para el bot
- Etapas del pipeline predefinidas
- Preguntas de calificación específicas del sector
- Nombres de entidades custom ("Paciente" en vez de "Lead")
