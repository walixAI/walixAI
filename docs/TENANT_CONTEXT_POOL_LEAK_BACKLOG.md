# Backlog: Fuga de contexto de tenant entre sesiones bajo contención del pool de conexiones

> Fecha: 2026-08-25. Hallazgo surgido del diagnóstico de "el bot no envía
> WhatsApp" / "process_message crashea intermitentemente" — dos incidentes
> reales confirmados con logs de Railway (Erick 01:57 UTC, Antonio 17:08 y
> 17:31 UTC). Mitigado puntualmente en `review/mitigate-tenant-context-pool-leak`;
> este documento registra el hallazgo completo, lo mitigado, lo NO auditado
> todavía, y el fix arquitectónico correcto pendiente.

---

## 1. El hallazgo

**No es un problema de `is_local`.** `set_tenant_context()`
(`backend/app/core/database.py:57-73`) ya usa `set_config('app.current_tenant_id',
:tid, FALSE)` — sesión, no transacción-local — en los tres call-sites
auditados. No existe ningún parámetro `is_local` en la función; la hipótesis
original de "está mal puesto en TRUE" fue descartada con evidencia directa
antes de investigar la causa real.

**La causa real:** SQLAlchemy libera la conexión física de Postgres de
vuelta al pool cuando una `AsyncSession` hace `commit()` (comportamiento
"connectionless" por defecto — la sesión no retiene la conexión entre
transacciones). La siguiente query de esa MISMA `AsyncSession`, al necesitar
una conexión de nuevo, puede recibir una conexión física **distinta** del
pool. `set_config(..., FALSE)` fija el GUC a nivel de la conexión física que
lo ejecutó — no del objeto `AsyncSession` de Python. Si la siguiente query
aterriza en otra conexión, esa conexión puede:

- No tener `app.current_tenant_id` seteado en absoluto (si es una conexión
  nueva del pool, `current_setting(..., true)` devuelve `NULL` — inofensivo
  bajo RLS, ya que `tenant_id = NULL` no matchea ninguna fila).
- Tener el valor de **otro tenant/sesión** que usó esa misma conexión antes
  y cuyo `set_config` nunca se limpió (el valor persiste en la conexión
  hasta el próximo `set_config`/reset explícito — un `commit()`/`rollback()`
  no lo borra).
- Tener literalmente `''` (string vacío) — origen exacto no identificado con
  certeza; probablemente otro caller que llama `set_config('app.current_tenant_id',
  '', ...)` en algún punto no auditado, o un valor derivado que termina
  vacío antes de llegar a `set_config`.

Bajo el rol de conexión actual (`postgres`, `rolbypassrls=true`,
`rolsuper=true` — confirmado con `SELECT rolname, rolbypassrls, rolsuper
FROM pg_roles WHERE rolname = current_user`), esto **no causa fuga de
datos real** porque RLS nunca se evalúa para este rol — confirmado
también en el docstring de `app/middleware/tenant_context.py:13-15`:
*"background tasks that use AsyncSessionLocal() directly bypass this
middleware. They run as the admin DB user which is a superuser and
bypasses RLS automatically."* El síntoma visible hoy es solo el crash
`asyncpg.exceptions.InvalidTextRepresentationError: invalid input syntax
for type uuid: ""` cuando el valor recibido resulta ser `''` en vez de un
UUID válido o `NULL`.

**Ver punto 5 — por qué esto es bloqueante para activar `walix_app` (rol
real, sin `BYPASSRLS`) en producción.**

---

## 2. La prueba

Reproducido directamente contra la base real (no solo teoría), simulando el
patrón exacto de las funciones afectadas: `set_config(marker_propio, FALSE)`
→ `commit()` → leer `current_setting()` de vuelta, con 40 sesiones
concurrentes (`asyncio.gather`):

```
total=40 mismatches=10
 MISMATCH: (20, 'marker-20-317546', 'marker-27-f5869e', False)
 MISMATCH: (21, 'marker-21-841022', 'marker-28-d47d8d', False)
 MISMATCH: (23, 'marker-23-97d934', 'marker-20-317546', False)
 ... (10 de 40, 25%)
```

10 de 40 sesiones (25%), tras hacer `commit()`, leyeron de vuelta el
marcador de **otra sesión** — no solo un valor vacío, sino contaminación
cruzada real entre "tenants" simulados.

Tras aplicar la mitigación puntual (reafirmar `set_tenant_context` justo
después de cada `commit()`), el mismo experimento con 40 sesiones
concurrentes: **0/40 mismatches**. Script de reproducción y verificación:
`backend/scripts/test_tenant_context_pool_mitigation.py`.

Evidencia de producción (Railway, logs reales, no simulados):

```
2026-08-25 17:08:07.643 UTC [12749] ERROR:  invalid input syntax for type uuid: ""
2026-08-25 17:08:07.643 UTC [12749] STATEMENT:  INSERT INTO messages (...) VALUES ($1::UUID, ...)
```
```
File "/app/app/ai/qualifier.py", line 178, in qualify_lead
    await db.refresh(lead)
...
sqlalchemy.exc.DBAPIError: ... invalid input syntax for type uuid: ""
[SQL: SELECT leads.branch_id, ... FROM leads WHERE leads.id = $1::UUID]
```
Este segundo caso (`qualifier.py`) confirma que **no es un problema de
concurrencia intra-sesión** — la sesión de `qualify_lead` es 100%
secuencial (un solo `await` a la vez, sin `asyncio.gather()` ni tareas
paralelas tocando esa sesión), y aun así el `db.refresh(lead)` inmediato
después del único `commit()` de esa sesión falló con el mismo error.

---

## 3. Call-sites

### Mitigados (`review/mitigate-tenant-context-pool-leak`)

| # | Archivo | Commit protegido | Query protegida |
|---|---|---|---|
| 1 | `backend/app/ai/bot_engine.py` — paso 4a | `commit()` del evento de memoria AI | `update_entity_context_task.delay(...)` y todo lo que sigue en la sesión |
| 2 | `backend/app/ai/bot_engine.py` — paso 4b | `commit()` de `AIOutcomeFeedback` | todo lo que sigue en la sesión (incluido el commit del paso 11) |
| 3 | `backend/app/ai/bot_engine.py` — paso 11 | `commit()` que persiste el mensaje del bot (el que falló en producción, Erick y Antonio) | pasos 11b-14 (scoring, Redis, envío WhatsApp) |
| 4 | `backend/app/ai/qualifier.py::qualify_lead` | `commit()` que persiste la calificación (línea ~177) | `db.refresh(lead)` y `advance_lead_stage`/`detect_risk`/`notify_assistant`/`escalate_to_human` |

Patrón aplicado en los 4 puntos: `await set_tenant_context(db, tenant_id)`
inmediatamente después de cada `commit()`, antes de la siguiente query.
Verificado con `test_tenant_context_pool_mitigation.py` (0/40 mismatches,
15/15 invocaciones reales de `_process_message_inner` sin fallo de uuid) y
regresión completa (`test_rls.py` 5/5, `test_webhook.py`,
`test_lead_scoring_task.py`, `test_whatsapp_send_visibility.py`).

### NO auditados todavía (fuera de alcance de esta mitigación)

Cualquier función que llame `set_tenant_context()` una vez y luego haga
**más de un** `commit()` sobre la misma `AsyncSession` está potencialmente
expuesta al mismo mecanismo. Confirmado por grep que usan el patrón
`set_tenant_context` + sesión propia (`AsyncSessionLocal()` directo, no
`get_db()`), pendientes de revisar cuántos commits hace cada uno y si
alguno tiene queries después del primer commit:

- `backend/app/api/webhooks.py` — el flujo de resolución de tenant
  (`fn_lookup_tenant_by_wa_phone_id` + `set_tenant_context`) antes de
  invocar `process_message` en background.
- `backend/app/services/prediction_service.py::_score_inner` — un solo
  commit al final según lectura previa del código (prompt de scoring,
  2026-08-25), probablemente NO expuesto, pero no confirmado con el mismo
  rigor que los 4 call-sites de arriba.
- `backend/app/ai/contact_executor.py`
- `backend/app/ai/copilot_tools.py` (varias ramas de `execute_tool`)
- `backend/app/ai/command_interpreter.py`
- `backend/app/agents/*.py` (executor, closing_agent, follow_up_agent,
  pipeline_agent, profile_enrichment_agent, reactivation_agent,
  config_agent, aprendiz_agent)
- `backend/app/tasks/*.py` (agent_tasks, ai_memory_tasks, alerts_tasks,
  dlq_handler, finance_tasks, metrics_tasks, _helpers)
- `backend/app/services/alert_generator.py`, `industry_inference.py`,
  `tenant_setup.py`
- `backend/app/api/internal_wa.py`
- `qualifier.py::advance_lead_stage`/`notify_assistant`/`escalate_to_human`
  (líneas ~222, ~247, ~297 según el comentario original del archivo) — cada
  una hace su propio `commit()` adicional DESPUÉS del punto ya mitigado
  (línea 178); no se confirmó si también necesitan reafirmación.

**No asumir que estos están bien** — la única razón por la que no han
producido un incidente reportado todavía es que no se ha buscado
activamente, no que estén confirmados como seguros.

---

## 4. Fix arquitectónico correcto (pendiente, no implementado)

La mitigación actual parchea cada call-site individualmente — funciona,
pero no escala (cada función nueva que combine `set_tenant_context` +
múltiples commits hereda el mismo riesgo si nadie recuerda aplicar el
patrón) y no cierra el problema en los call-sites de la sección 3 aún no
auditados.

**Dirección correcta: un listener a nivel de pool de SQLAlchemy
(`PoolEvents.checkout`)** — en vez de que cada función recuerde reafirmar
el contexto, enganchar un handler que se dispare en **cada** checkout de
una conexión física del pool (`sqlalchemy.event.listens_for(engine.sync_engine,
"checkout")` o equivalente async), y ahí:

- Opción A — **limpiar** el GUC en cada checkout (`RESET app.current_tenant_id`
  o `set_config('app.current_tenant_id', '', true)` con verdadero
  `is_local`/transacción), forzando que CADA función que necesite contexto
  de tenant lo vuelva a setear explícitamente al principio de su propio uso
  — falla de forma segura (RLS bloquea todo por defecto) en vez de heredar
  el contexto de quien usó la conexión antes.
- Opción B — mantener un registro externo (fuera de la conexión Postgres,
  ej. una `ContextVar` de Python asociada a la `AsyncSession`) de "cuál es
  el tenant_id que ESTA sesión lógica debería tener seteado", y que el
  listener de `checkout` reaplique automáticamente ese valor a la conexión
  física recién obtenida, sin que cada función tenga que acordarse.

Cualquiera de las dos opciones requiere diseño explícito (qué pasa con
sesiones que nunca llamaron `set_tenant_context`, cómo interactúa con
`get_db()`/`TenantContextMiddleware`, overhead por request) — no se
implementó en este backlog a propósito, para no resolver una decisión de
arquitectura como efecto colateral de una mitigación de incidente.

---

## 5. Bloqueante — no activar `walix_app` sin resolver esto primero

**Esto es explícitamente bloqueante para el plan ya documentado en
`app/core/config.py` de migrar `DATABASE_URL`/`effective_database_url` del
rol admin actual al rol `walix_app` (sin `BYPASSRLS`) en producción.**

Hoy el bug es inofensivo en cuanto a aislamiento de datos porque el rol de
conexión (`postgres`, superusuario, `BYPASSRLS=true`) nunca evalúa las
policies de RLS — la fuga de contexto solo se manifiesta como el crash de
uuid vacío, no como acceso cruzado real. **Bajo `walix_can_app` (sin
bypass), la MISMA fuga de contexto demostrada en la sección 2 significaría
que una sesión puede terminar operando con el `app.current_tenant_id` de
OTRO tenant después de un commit** — es decir, ver y potencialmente escribir
filas de un tenant ajeno, no solo un crash. El experimento de 40 sesiones
concurrentes (10/40 = 25% de contaminación cruzada) da una idea de la
frecuencia esperable bajo carga real si se activara `walix_app` sin
resolver esto a nivel de pool primero.

**No activar `walix_app` como rol de runtime en producción hasta que el fix
arquitectónico de la sección 4 esté implementado y verificado** — la
mitigación puntual de la sección 3 NO es suficiente para ese cambio,
porque solo cubre 4 call-sites confirmados de un universo más grande no
auditado (sección 3).
