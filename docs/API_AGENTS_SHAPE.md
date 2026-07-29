# Shape exacto de la API de sugerencias de IA

> Fuente: `backend/app/api/agents.py`, modelos y agentes. Fecha: 2026-06-22.

---

## 1. GET /api/agents/suggestions

### Estructura de la respuesta

**Array plano** — `list[SuggestionOut]`. Sin wrapper, sin paginación.

```json
[
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "agent_type": "follow_up",
    "trigger_description": "Lead inactivo 27h sin respuesta",
    "suggestion_text": "María García lleva 27h sin responder. Sugerencia: reenviar saludo.",
    "action_payload": {
      "lead_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "message": "¡Hola María! ¿Pudiste revisar la información que te enviamos?"
    },
    "target_role": "asesor",
    "target_user_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "status": "suggested",
    "execution_result": null,
    "error_detail": null,
    "responded_at": null,
    "expires_at": "2026-06-24T14:30:00Z",
    "created_at": "2026-06-22T14:30:00Z",
    "updated_at": "2026-06-22T14:30:00Z"
  }
]
```

### Tipos de cada campo

| Campo | Tipo TS | Nullable | Notas |
|---|---|---|---|
| `id` | `string` (UUID) | no | |
| `agent_type` | `string` | no | Ver valores abajo |
| `trigger_description` | `string` | no | Truncado a ≤80 chars |
| `suggestion_text` | `string` | no | Truncado a ≤120–200 chars según agente |
| `action_payload` | `object \| null` | sí | Varía por `agent_type` — ver §4 |
| `target_role` | `string` | no | `"asesor" \| "gerente" \| "owner"` |
| `target_user_id` | `string \| null` | sí | UUID del usuario destinatario; null = broadcast a todos con ese rol |
| `status` | `string` | no | `"suggested" \| "accepted" \| "confirmed" \| "executed" \| "dismissed" \| "expired" \| "failed"` |
| `execution_result` | `object \| null` | sí | Resultado tras ejecutar (ver §4 por agent_type) |
| `error_detail` | `string \| null` | sí | Mensaje si `status === "failed"` |
| `responded_at` | `string \| null` | sí | ISO 8601 UTC; se pone al confirmar o descartar |
| `expires_at` | `string` | no | ISO 8601 UTC; siempre NOW + 48h al crear |
| `created_at` | `string` | no | ISO 8601 UTC |
| `updated_at` | `string` | no | ISO 8601 UTC |

> **Campos ausentes del response:** `tenant_id` y `branch_id` están en el modelo DB pero NO se exponen en `SuggestionOut` — el endpoint ya filtra por tenant del usuario autenticado.

### Lógica de filtrado del GET

El endpoint devuelve solo sugerencias con `status === "suggested"` que cumplan:
- `target_user_id === usuario_autenticado.id`, **O**
- `target_user_id === null` AND `target_role === usuario_autenticado.role`

Expira in-band (bulk UPDATE a `"expired"`) las sugerencias caducadas antes de devolver la lista.

---

## 2. Formato: array plano o wrapped

**Array plano.** La respuesta es directamente `[{...}, {...}]`, sin envoltura.

```typescript
// tipo exacto del response
type GetSuggestionsResponse = SuggestionOut[];
```

---

## 3. POST /confirm y POST /dismiss

### POST /api/agents/suggestions/{id}/confirm

- **Body:** ninguno (sin body)
- **Respuesta:** `202 Accepted` + el objeto `SuggestionOut` actualizado
- **Qué cambia:** `status → "confirmed"`, `responded_at → now()`
- **Efecto lateral:** encola `execute_suggestion_task` en Celery (el worker lo ejecuta async)
- **Error:** `409 Conflict` si `status` ya no es `"suggested"` ni `"accepted"`

```typescript
// sin body
fetch(`/api/agents/suggestions/${id}/confirm`, { method: "POST" })
// devuelve SuggestionOut con status: "confirmed"
```

### POST /api/agents/suggestions/{id}/dismiss

- **Body:** `{ "reason": string | null }` — el campo `reason` es opcional
- **Respuesta:** `200 OK` + el objeto `SuggestionOut` actualizado
- **Qué cambia:** `status → "dismissed"`, `responded_at → now()`, si hay `reason` se guarda en `execution_result: { "dismissed_reason": reason }`
- **Error:** `409 Conflict` si `status` ya no es `"suggested"` ni `"accepted"`

```typescript
fetch(`/api/agents/suggestions/${id}/dismiss`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ reason: "No aplica por ahora" }) // o { reason: null }
})
// devuelve SuggestionOut con status: "dismissed"
```

---

## 4. action_payload por agent_type

El payload varía por agente. Aquí la forma estable de cada uno:

### `follow_up`

```json
{
  "lead_id": "a1b2c3d4-...",
  "message": "¡Hola María! ¿Pudiste revisar la información que te enviamos?"
}
```
Al ejecutarse: envía el `message` vía WhatsApp al `lead.wa_phone`. Registra actividad `REPLY`.

---

### `closing`

```json
{
  "lead_id": "a1b2c3d4-...",
  "proposal_text": "Hola Juan, te propongo iniciar tu tratamiento esta semana por $3,500. ¿Tienes disponibilidad el martes?"
}
```
Al ejecutarse: envía `proposal_text` vía WA, registra actividad `QUOTE`, y avanza el lead a la siguiente etapa del pipeline.

---

### `reactivation`

```json
{
  "lead_id": "a1b2c3d4-...",
  "message": "Hola Pedro, hace tiempo no sabemos de ti. ¿Podemos ayudarte con algo?"
}
```
Al ejecutarse: no hay `_exec_reactivation` en `executor.py` — `_dispatch()` lanzaría `ValueError: Unknown agent_type: reactivation`. **Bug latente:** el executor no implementa este tipo todavía.

---

### `profile_enrichment`

```json
{
  "lead_id": "a1b2c3d4-...",
  "company": "Clínica Santa Fe"
}
```
Al ejecutarse: igual que `reactivation`, no hay `_exec_profile_enrichment` en `executor.py`. **Bug latente** — si el usuario confirma, falla con 500.

---

### `pipeline`

El más complejo. `action` determina la sub-acción:

```json
{
  "action": "create_task",
  "bottleneck_stages": [
    { "stage_id": "uuid", "stage_name": "Primera Cita", "total": 12, "stalled": 8, "stalled_pct": 67 }
  ],
  "low_conversion_asesores": [
    { "asesor_id": "uuid", "asesor_name": "Carlos R.", "total": 10, "won": 1, "conversion_pct": 10 }
  ]
}
```

```json
{
  "action": "reassign",
  "leads": ["uuid1", "uuid2"],
  "to_asesor_id": "uuid-del-asesor",
  "bottleneck_stages": [...],
  "low_conversion_asesores": [...]
}
```

```json
{
  "action": "archive_stage",
  "stage_id": "uuid-de-la-etapa",
  "inactive_stages": [
    { "stage_id": "uuid", "stage_name": "Estudios Avanzados", "current_leads": 0, "recent_activity": 0 }
  ]
}
```

---

### `config`

```json
{
  "action": "deactivate_stage",
  "inactive_stages": [
    { "stage_id": "uuid", "stage_name": "Estudios Avanzados", "current_leads": 0, "recent_activity": 0 }
  ],
  "action_detail": {
    "stage_id": "uuid-de-la-etapa"
  }
}
```

```json
{
  "action": "no_action",
  "inactive_stages": [...]
}
```

---

## 5. execution_result tras ejecutar

Cuando `status === "executed"`, `execution_result` contiene el resultado de la acción:

| agent_type | execution_result |
|---|---|
| `follow_up` | `{ "sent": true, "lead_id": "...", "message": "..." }` |
| `closing` | `{ "sent": true, "lead_id": "...", "proposal_text": "...", "advanced_to_stage": "uuid \| null" }` |
| `pipeline` (create_task) | `{ "action": "create_task", "note": "Revisión de pipeline requerida: ..." }` |
| `pipeline` (reassign) | `{ "action": "reassign", "reassigned": 3, "to_asesor_id": "..." }` |
| `pipeline` (archive_stage) | `{ "action": "archive_stage", "archived": true, "stage_id": "...", "stage_name": "..." }` |
| `config` (deactivate_stage) | `{ "action": "deactivate_stage", "applied": true, "stage_id": "...", "stage_name": "..." }` |
| `reactivation` | ❌ Falla — no implementado en executor |
| `profile_enrichment` | ❌ Falla — no implementado en executor |

Cuando `status === "dismissed"` con reason:
```json
{ "dismissed_reason": "No aplica por ahora" }
```

---

## Resumen para el frontend

```typescript
interface AiSuggestion {
  id: string;
  agent_type: "follow_up" | "pipeline" | "closing" | "config" | "reactivation" | "profile_enrichment";
  trigger_description: string;
  suggestion_text: string;
  action_payload: Record<string, unknown> | null;
  target_role: "asesor" | "gerente" | "owner";
  target_user_id: string | null;
  status: "suggested" | "accepted" | "confirmed" | "executed" | "dismissed" | "expired" | "failed";
  execution_result: Record<string, unknown> | null;
  error_detail: string | null;
  responded_at: string | null;   // ISO 8601 UTC
  expires_at: string;            // ISO 8601 UTC
  created_at: string;            // ISO 8601 UTC
  updated_at: string;            // ISO 8601 UTC
}

// GET /api/agents/suggestions → AiSuggestion[]
// POST /api/agents/suggestions/{id}/confirm  (sin body) → AiSuggestion (202)
// POST /api/agents/suggestions/{id}/dismiss  body: { reason?: string } → AiSuggestion (200)
```
