# Backlog: Inconsistencias de permisos/arquitectura (Prompt 0 — auditoría del catálogo del Copiloto)

> Fecha: 2026-08-19. Solo lectura — ningún archivo de código fue modificado para
> generar este documento.
>
> Este backlog salió de la auditoría "Prompt 0" hecha para inventariar las 192
> acciones de negocio de `app/api/` y compararlas contra el catálogo del
> Copiloto (`app/copilot/actions_catalog.py`, Fase 1). Los 6 hallazgos de abajo
> **no son huecos del catálogo** — son bugs/inconsistencias reales en la capa
> de autorización de la API REST, descubiertos como efecto colateral de leer
> cada endpoint. Quedan fuera de las 7 fases del plan del Copiloto; se
> documentan acá para atenderlos como trabajo propio más adelante.

---

## 1. `_MULTI_BRANCH_ROLES` divergente entre archivos

**Archivos:**
- `backend/app/api/leads.py:176` — `_MULTI_BRANCH_ROLES = (UserRole.OWNER, UserRole.IT)`
- `backend/app/api/pipeline.py:37` — `_MULTI_BRANCH_ROLES = (UserRole.OWNER, UserRole.IT)`
- `backend/app/api/pipelines.py:27` — `_MULTI_BRANCH_ROLES = (UserRole.OWNER, UserRole.IT)`
- `backend/app/api/users.py:201` — `_MULTI_BRANCH_ROLES = (UserRole.OWNER, UserRole.IT)`
- `backend/app/api/metrics.py:40` — `_MULTI_BRANCH_ROLES = {UserRole.OWNER, UserRole.IT, UserRole.PLATFORM_OWNER}`

**Problema:** un `platform_owner` tiene acceso cross-branch en los endpoints de
`metrics.py` (dashboard, sentiment, forecast, pipeline-intelligence) pero
**no** en los de `leads.py`/`pipeline.py`/`pipelines.py`/`users.py` — mismo
rol, comportamiento inconsistente según qué archivo resolvió la constante
localmente en vez de importarla de un solo lugar. Cada archivo la redefine
por separado; no hay una única fuente de verdad.

**Fix sugerido (no implementar ahora):** mover la constante a un módulo
compartido (ej. `app/core/roles.py`) e importarla en los 5 archivos, con
`PLATFORM_OWNER` incluido — que es el comportamiento que ya tiene
`app/copilot/permissions.py:32` (`_MULTI_BRANCH_ROLES = frozenset({OWNER, IT, PLATFORM_OWNER})`)
y `metrics.py`.

**Riesgo si no se corrige:** bajo-medio — es una inconsistencia de UX/acceso,
no una fuga de datos entre tenants (RLS sigue protegiendo el aislamiento
real).

*Nota al margen: existe un sexto archivo con la misma constante y los mismos
valores `(OWNER, IT)` — `backend/app/_deprecated/opportunities.py:38`. No se
cuenta como parte de este hallazgo porque `opportunities.py` no está montado
en `app/main.py` (código deprecado, ver `docs/OPPORTUNITY_VS_DEAL_AUDIT.md`),
pero si algún día se reactiva heredaría la misma divergencia.*

**✅ RESUELTO** (2026-08-22, ver commit de este cambio): se creó
`app/core/roles.py::MULTI_BRANCH_ROLES = frozenset({OWNER, IT,
PLATFORM_OWNER})` como única fuente de verdad, e importada en los 5
archivos (`leads.py`, `pipeline.py`, `pipelines.py`, `users.py`,
`metrics.py`), eliminando cada definición local. Esto amplía el acceso
cross-branch de `PLATFORM_OWNER` en `leads.py`/`pipeline.py`/
`pipelines.py`/`users.py` — es el fix esperado, no un efecto secundario.
`app/copilot/permissions.py:32` mantiene su propia copia idéntica sin
tocar (fuera de alcance de este cambio, evaluado y descartado por ahora —
ver mensaje del PR); `app/_deprecated/opportunities.py:38` tampoco se
tocó (código deprecado, no montado en `app/main.py`). Tests en
`backend/tests/regression/test_core_roles.py` y ajustes en las suites de
los 5 módulos.

---

## 2. `users.py::_require_owner` excluye PLATFORM_OWNER

**Archivo:** `backend/app/api/users.py:105-110`
```python
def _require_owner(user: User) -> None:
    if user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el owner puede realizar esta acción",
        )
```
Usado en `create_team_member` (`users.py:162`) y `toggle_active` (`users.py:282`).

**Problema:** exige **exactamente `UserRole.OWNER`**, sin incluir
`PLATFORM_OWNER` — a diferencia de todos los demás `_require_owner`/
`_OWNER_ROLES` del resto del código, que son `{OWNER, PLATFORM_OWNER}`:
`billing.py:118`, `finance.py:24`, `profitability.py:35`,
`walix_builder.py:51`. Un `platform_owner` puede gestionar billing, finanzas
y recetas del Builder de cualquier tenant, pero no puede crear miembros de
equipo ni activar/desactivar usuarios de ese mismo tenant.

**Fix sugerido (no implementar ahora):** cambiar la condición a
`user.role not in (UserRole.OWNER, UserRole.PLATFORM_OWNER)`, igual que el
resto del código.

**Riesgo si no se corrige:** bajo — es una limitación operativa para
`platform_owner` (tendría que asumir el rol del tenant o pedirle al owner
real), no un problema de seguridad.

**✅ RESUELTO** (2026-08-23, ver commit de este cambio): `_require_owner`
ahora exige `user.role not in (UserRole.OWNER, UserRole.PLATFORM_OWNER)`,
igual que el resto del código. No se creó una constante compartida en
`app/core/roles.py` para este patrón — está duplicado en varios archivos
más (`billing.py`, `finance.py`, `profitability.py`, `walix_builder.py`,
`tenant.py`), consolidarlos todos es un refactor más grande que este
hallazgo puntual, queda como decisión aparte. Tests en
`backend/tests/regression/test_users_require_owner_platform_owner.py`.

---

## 3. `industry_onboarding.py::_OWNER_ROLES` = `(OWNER,)` sin PLATFORM_OWNER

**Archivo:** `backend/app/api/industry_onboarding.py:48-52`
```python
_OWNER_ROLES = (UserRole.OWNER,)

def _require_owner(user: User) -> None:
    if user.role not in _OWNER_ROLES:
        ...
```
Usado en `get_industry_settings` (`industry_onboarding.py:269`) y
`change_industry` (`industry_onboarding.py:319`).

**Problema:** es la constante más restrictiva de todo el código — ni
siquiera incluye `IT` (a diferencia de `onboarding.py`'s
`_require_owner_it`), ni `PLATFORM_OWNER`. `change_industry` además
**recrea el pipeline completo del tenant** (acción destructiva, aunque
protegida por `confirm_reset=true`), lo cual hace más notable que
`platform_owner` no pueda tocarlo ni para soporte de emergencia.

**Fix sugerido (no implementar ahora):** decidir si `platform_owner` debería
tener este acceso (consistente con el resto de `_OWNER_ROLES` del código) o
si la restricción a solo `OWNER` es intencional para esta acción
específicamente (cambiar la industria de un tenant ajeno es una decisión de
negocio, no solo técnica) — no asumir automáticamente el patrón de los
demás archivos.

**Riesgo si no se corrige:** bajo — mismo tipo de limitación operativa que
el hallazgo 2, no una fuga de datos.

**✅ RESUELTO** (2026-08-23, ver commit de este cambio): `_OWNER_ROLES`
pasó a `(UserRole.OWNER, UserRole.PLATFORM_OWNER)`. Decisión de producto
explícita tomada en el chat (no asumida por el patrón de los demás
archivos, como pedía la nota de "fix sugerido" de arriba): `PLATFORM_OWNER`
SÍ debe poder ver **y** cambiar la industria de un tenant, incluyendo
`change_industry` (acción destructiva que recrea el pipeline completo) —
deliberado, no un descuido.

Nota de diseño importante descubierta al implementar: ni
`get_industry_settings` ni `change_industry` aceptan un `tenant_id`
objetivo — ambos operan exclusivamente sobre `current_user.tenant_id`, a
diferencia de `app/api/platform.py`, donde las operaciones cross-tenant de
`PLATFORM_OWNER` sí reciben `tenant_id` explícito. Este fix solo permite
que un usuario con rol `PLATFORM_OWNER` gestione la industria de **su
propio tenant** — no la de un tenant ajeno, porque el endpoint no tiene
ningún mecanismo para apuntar a otro tenant. Habilitar eso de verdad
requeriría rediseñar el endpoint (agregar `tenant_id`, posiblemente mover
a `platform.py`) — quedó fuera de alcance de este hallazgo puntual, es una
decisión aparte si se quiere ese alcance real.

Tests en `backend/tests/regression/test_industry_onboarding_owner_roles.py`
— incluye verificación real de que `change_industry` archiva las etapas
viejas y crea las nuevas del template (no solo status 200).

---

## 4. `automations.py::_OWNER_PLUS` incluye IT, no coincide con `app/copilot/actions_catalog.py::_OWNER_TIER`

**Archivos:**
- `backend/app/api/automations.py:22` — `_OWNER_PLUS = {UserRole.OWNER, UserRole.IT, UserRole.PLATFORM_OWNER}`
- `backend/app/copilot/actions_catalog.py:49` — `_OWNER_TIER = frozenset({UserRole.OWNER, UserRole.PLATFORM_OWNER})`

Usado en `patch_automation` (`automations.py:111`) y `re_execute_automation`
(`automations.py:145`).

> Corrección sobre el prompt original: `_OWNER_TIER` no vive en
> `app/copilot/permissions.py` (ese archivo solo tiene `_MULTI_BRANCH_ROLES`,
> línea 32) — vive en `app/copilot/actions_catalog.py:49`. Verificado contra
> el código real antes de escribir esto.

**Problema:** `_OWNER_PLUS` incluye `IT` además de `OWNER`/`PLATFORM_OWNER`;
`_OWNER_TIER` (el criterio que ya usa el catálogo del Copiloto para acciones
de alto riesgo tipo `cancel_subscription`) no incluye `IT`. Son dos
definiciones de "nivel owner" con membresía distinta conviviendo en el
mismo backend.

**Nota específica para este hallazgo:** si algún día se conecta
`re_execute_automation` (re-ejecutar una sugerencia descartada/fallida) al
catálogo del Copiloto — es una acción de escritura que dispara ejecución
real, candidata natural a entrar como acción del catálogo — hay que decidir
explícitamente **cuál de los dos criterios de rol es el correcto** antes de
conectarla: si se usa `_OWNER_TIER` (sin IT) se restringe respecto al
comportamiento actual del endpoint REST; si se mantiene `_OWNER_PLUS` (con
IT) el catálogo queda con un criterio de rol que no coincide con el patrón
que usa para otras acciones de riesgo alto/medio gateadas a owner.

**Fix sugerido (no implementar ahora):** no fusionar automáticamente los dos
sets — decidir en el chat, con el contexto de qué tan sensible es cada
acción, si `IT` debería tener este nivel de acceso de forma consistente en
todo el código o si `automations.py` es el que está mal.

**Riesgo si no se corrige:** bajo — hoy no hay conexión real entre ambos
archivos, es una inconsistencia latente que solo importa el día que se
conecten.

**✅ RESUELTO** (2026-08-23, ver commit de este cambio): decisión de
producto tomada en el chat — `IT` SÍ debe tener el mismo nivel de acceso
que `OWNER`/`PLATFORM_OWNER` para gestionar automatizaciones, es decir,
`automations.py::_OWNER_PLUS` (que ya incluye `IT`) es el comportamiento
correcto, **no** `actions_catalog.py::_OWNER_TIER`. Esto NO fue un fix de
código — `automations.py` ya estaba correcto tal como estaba y no se
tocó. `_OWNER_TIER` tampoco se modificó globalmente (sigue sin `IT`,
correcto para `cancel_subscription`, `get_team_performance` y
`list_finance_permissions`, que deben seguir siendo más restrictivos).
Se agregó un comentario defensivo justo antes de la definición de
`_OWNER_TIER` en `actions_catalog.py` explicando esta divergencia
intencional, para que si algún día se conecta `re_execute_automation` o
`patch_automation` al catálogo, quien lo haga use un set que incluya `IT`
(como `_OWNER_PLUS`) en vez de reutilizar `_OWNER_TIER` por costumbre. No
hizo falta ningún test nuevo — no cambia comportamiento de ningún endpoint
ni tool; se corrió `test_copilot_actions_catalog.py` como chequeo de que
tocar el archivo no rompió nada (sin cambios de resultado esperados).

---

## 5. `delete_deal` sin restricción de rol en el endpoint REST real

**Archivo:** `backend/app/api/deals.py:393-401`
```python
@router.delete("/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    deal = await _get_deal_or_404(deal_id, current_user.tenant_id, db)
    await db.delete(deal)
    await db.commit()
```

**Problema:** cualquier usuario autenticado del tenant —sin importar su
rol— puede borrar permanentemente (hard delete, no soft delete) cualquier
deal del tenant. No hay ningún `if current_user.role ...` en todo el
handler, solo `Depends(get_current_user)` (cualquier sesión válida) y el
scoping de tenant vía `_get_deal_or_404`. Ya estaba señalado como comentario
en `app/copilot/actions_catalog.py` (la acción stub `delete_deal`), este
documento lo deja registrado formalmente con la línea exacta.

**Fix sugerido (no implementar ahora):** agregar un check de rol (candidatos
naturales: `_MANAGER_ROLES`-style como en `contacts.py::delete_contact`, o
restringir a owner-tier dado que es irreversible) — decidir el criterio
correcto en el chat antes de tocar el endpoint.

**Riesgo si no se corrige:** **alto** — es el único de los 6 hallazgos con
riesgo real de daño: un `asesor` puede borrar deals de otros vendedores o
del owner sin ninguna restricción, de forma irreversible.

**✅ RESUELTO** (2026-08-20, ver commit de este cambio): `delete_deal` ahora
exige `current_user.role in _MANAGER_ROLES` (`OWNER`, `GERENTE`, `IT`) O
`deal.owner_id == current_user.id` — mismo criterio que
`contacts.py::delete_contact` (`_MANAGER_ROLES` + ownership), definido
localmente en `deals.py` porque `_MANAGER_ROLES` es privada de
`contacts.py`. Si no cumple ninguna condición: `403` con detalle "No tienes
permiso para eliminar este deal". `create_deal` y `update_deal` quedan
fuera de alcance a propósito. Tests en
`backend/tests/regression/test_deals_delete_permission.py`.

---

## 6. `set_monthly_goal` del Copiloto y `goals.py::create_or_update_monthly_goal` son implementaciones paralelas, no el mismo camino de código

**Archivos:**
- `backend/app/ai/copilot_tools.py:1068` — `if name == "set_monthly_goal":` (rama del dispatcher `execute_tool`, lógica de upsert propia sobre el modelo `MonthlyGoal`)
- `backend/app/api/goals.py:254` — `async def create_or_update_monthly_goal(` (endpoint REST `POST /goals/monthly-goals`, también upsert sobre `MonthlyGoal`, con su propio registro en `MonthlyGoalHistory`)

**Problema:** ambos caminos hacen esencialmente lo mismo (upsert de la meta
mensual global, con historial) pero son dos implementaciones de código
completamente independientes — no hay ninguna llamada de uno al otro. Si se
cambia la lógica de negocio en un lado (ej. una nueva validación, un campo
extra en `MonthlyGoalHistory`), hay que recordar replicarlo manualmente en
el otro o divergen en silencio.

**Fix sugerido (no implementar ahora) — distinto a los hallazgos 1-5:** acá
no es un tema de roles. Dos caminos posibles a decidir más adelante:
(a) que la tool del Copiloto llame internamente a la función/servicio que
usa el endpoint REST (unificar en una sola implementación), o
(b) aceptar la duplicación como deuda técnica documentada, si hay una razón
real para que sean independientes (ej. la tool del Copiloto no puede
depender de código de `app/api/`).

**Riesgo si no se corrige:** bajo — ambos caminos funcionan hoy; el riesgo
es de mantenimiento futuro (drift silencioso), no de seguridad ni de datos
incorrectos en el estado actual.

**✅ RESUELTO** (2026-08-23): se implementó la opción (a) — se unificó la
lógica de negocio en `backend/app/services/goals_service.py::
upsert_monthly_goal` (validar periodo pasado, buscar meta existente,
upsert, registrar `MonthlyGoalHistory`), y ahora tanto
`goals.py::create_or_update_monthly_goal` como la rama `set_monthly_goal`
de `copilot_tools.py::execute_tool` llaman a ese servicio compartido en
vez de reimplementar la lógica cada uno por su lado. El chequeo de acceso
(`_require_finance_access` en el REST, `require_finance_access` en el
Copiloto) y el flujo `confirmed=bool` propio del Copiloto se quedaron
fuera del servicio — son responsabilidad de cada caller, no lógica de
negocio de la meta en sí.

**Gap de acceso encontrado durante este fix (no es el hallazgo #6
original, que era solo sobre duplicación):** al auditar el código para
unificarlo se confirmó que la rama `set_monthly_goal` del Copiloto **no**
llamaba a `require_finance_access` — a diferencia de su endpoint REST
equivalente y del resto de tools de finanzas del Copiloto (hallazgo #8).
Cualquier usuario autenticado podía setear la meta mensual global vía el
Copiloto sin ningún chequeo de acceso a finanzas. Se corrigió agregando
`require_finance_access(user, None, db)` al inicio de la rama, ANTES del
flujo `confirmed=bool` — así un usuario sin acceso no ve ni el mensaje de
confirmación con el monto propuesto. Tests nuevos en
`tests/regression/test_copilot_set_monthly_goal_access.py` cubren: ASESOR
sin `FinancePermission` denegado (y sin crear nada en BD), OWNER con
bypass por rol, ASESOR con `FinancePermission` tenant-wide permitido, el
orden acceso-antes-que-confirmación, y un upsert real (crear → actualizar)
verificando que `MonthlyGoalHistory` registra `goal_created` y
`goal_updated` igual que antes del refactor.

---

## 7. `confirm_suggestion`/`dismiss_suggestion` sin validación de ownership

**Archivo(s):**
- `backend/app/api/agents.py:162-171` — `_get_suggestion_for_user`, el helper que usan ambos endpoints:
  ```python
  async def _get_suggestion_for_user(
      suggestion_id: uuid.UUID,
      user: User,
      db: AsyncSession,
  ) -> AgentSuggestion:
      """Load suggestion and verify it belongs to the user's tenant."""
      suggestion = await db.get(AgentSuggestion, suggestion_id)
      if suggestion is None or suggestion.tenant_id != user.tenant_id:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
      return suggestion
  ```
- `backend/app/api/agents.py:100-124` — `confirm_suggestion`, llama al helper en la línea 106
- `backend/app/api/agents.py:131-157` — `dismiss_suggestion`, llama al helper en la línea 138
- Contraste — `backend/app/api/agents.py:53-92` — `list_suggestions`, que SÍ filtra por ownership (líneas 82-86):
  ```python
  or_(
      AgentSuggestion.target_user_id == current_user.id,
      (AgentSuggestion.target_user_id.is_(None))
      & (AgentSuggestion.target_role == current_user.role.value),
  ),
  ```

**Problema:** `_get_suggestion_for_user` solo valida `tenant_id` — pese a que
su propio docstring dice "verify it belongs to the user's tenant" (línea 167),
no valida que la sugerencia esté dirigida al usuario (`target_user_id`) ni a
su rol (`target_role`), a diferencia de `list_suggestions`, que sí aplica
ese filtro antes de devolver la lista. El resultado: `confirm_suggestion` y
`dismiss_suggestion` aceptan cualquier `suggestion_id` que pertenezca al
tenant del usuario, sin importar a quién estaba dirigida.

No es "cualquiera puede confirmar cualquier sugerencia sin saber nada" — el
UUID no aparece en ningún listado si la sugerencia no es del usuario que
consulta (`list_suggestions` ya la filtra fuera). Pero sigue siendo un hueco
real: un miembro del equipo que vea el UUID en logs del servidor, en la URL
de otro usuario, o por fuerza bruta de un UUID conocido de otra fuente,
podría confirmar o descartar una sugerencia ajena — y confirmarla dispara
`execute_suggestion_task.delay(...)` (`agents.py:119`), es decir, ejecución
real del `agent_type` correspondiente (puede incluir enviar un WhatsApp a un
lead, mover un deal de etapa, u otras acciones dependiendo del agente que la
generó).

**Relevante para el trabajo en curso:** este hallazgo salió justo al auditar
cómo conectar `confirm_suggestion`/`dismiss_suggestion` al catálogo del
Copiloto. Si se conectan tal cual, el catálogo heredaría el mismo hueco de
ownership — conviene corregirlo antes o en paralelo a esa conexión, no
después.

**Fix sugerido (no implementar ahora):** agregar dentro de
`_get_suggestion_for_user` el mismo filtro de `target_user_id`/`target_role`
que ya usa `list_suggestions`, en vez de duplicar la condición `or_(...)` en
cada endpoint que necesite cargar una sugerencia por ID.

**Riesgo si no se corrige:** medio — no es explotable sin conocer un UUID
específico (no hay enumeración trivial vía la API), pero si se conoce uno,
la consecuencia es ejecución real de una acción de negocio ajena, no solo
lectura de datos.

**✅ RESUELTO** (2026-08-23): `_get_suggestion_for_user` ahora aplica el
mismo filtro de ownership que `list_suggestions` (`target_user_id ==
usuario`, O `target_user_id IS NULL` y `target_role == rol del usuario`),
centralizado en el helper — `confirm_suggestion` y `dismiss_suggestion`
no duplican la condición, siguen llamándolo igual que antes. El chequeo
de `tenant_id` se mantiene en la misma query. La respuesta ante fallo
sigue siendo 404 (sin cambios de status code, solo cambió qué filtra la
query).

El mismo problema ya se había resuelto del lado del Copiloto
(`app/ai/copilot_tools.py::execute_tool`, rama `dismiss_suggestion`, ver
`tests/regression/test_copilot_dismiss_suggestion.py`) en un commit
anterior de esta sesión, precisamente para no heredar este hueco al
conectar el catálogo — ese fix construía su propia query con el mismo
criterio en vez de reutilizar este helper, porque en ese momento el
helper REST seguía siendo el que solo validaba `tenant_id`. Este cambio
cierra el lado REST que había quedado pendiente entonces.

Tests nuevos en `tests/regression/test_agents_suggestion_ownership.py`
(vía los endpoints REST reales con `client`, mockeando
`execute_suggestion_task.delay` para no encolar un job real contra el
Redis compartido del entorno): dirigida a otro usuario específico →
404 sin cambiar estado (confirm y dismiss), dirigida directamente al
usuario → sigue funcionando, dirigida a su rol (broadcast) → sigue
funcionando, dirigida a otro rol → 404, y otro tenant → 404 confirmado
explícitamente ahora que se tocó la función.

---

## 8. Tools de finanzas del Copiloto sin validar `FinancePermission`

**Archivo(s):**
- `backend/app/ai/copilot_tools.py::execute_tool`, ramas `"get_profitability"`
  (antes de este fix, ~línea 659), `"get_run_rate"` (~línea 668) y
  `"get_expenses_summary"` (~línea 677) — ejecutaban directo, sin ningún
  chequeo de acceso.
- Contraste — `backend/app/api/finance.py:29-47` (`_require_finance_access`)
  y `backend/app/api/profitability.py:91,108,188` — los endpoints REST
  equivalentes SÍ exigen `_require_finance_access` antes de responder.

**Problema:** el Copiloto mostraba rentabilidad, run-rate y resumen de
gastos a cualquier usuario autenticado del tenant, incluso a alguien a
quien el Owner le negó explícitamente acceso a finanzas (sin fila en
`FinancePermission`) — mismo dato que el endpoint REST equivalente le
habría bloqueado con 403.

**✅ RESUELTO** (2026-08-21, ver commit de este cambio): se creó
`app/copilot/finance_access.py::require_finance_access`, que replica
`_require_finance_access` exactamente (OWNER/PLATFORM_OWNER siempre
permitido; el resto requiere una fila en `FinancePermission` para su
tenant con `branch_id` igual al solicitado o `branch_id IS NULL`), pero
retorna `(allowed, reason)` en vez de levantar `HTTPException` — mismo
contrato que `app/copilot/permissions.py::check_permission`, ya que
`execute_tool` nunca levanta excepciones crudas. Las 3 ramas ahora llaman
`require_finance_access(user, None, db)` (mismo `branch_id=None` que usan
sus endpoints REST equivalentes) antes de ejecutar, devolviendo
`{"error": "No tienes acceso a finanzas"}` si no hay acceso. Tests en
`backend/tests/regression/test_copilot_finance_access.py`. No se conectó
ninguna acción nueva de finanzas en este cambio — solo se cerró el gap de
las 3 tools ya wireadas.

**Riesgo si no se corrige:** alto — exposición directa de datos
financieros del tenant (rentabilidad, gastos) a usuarios explícitamente
sin acceso, saltándose un control de acceso que el resto de la app sí
respeta.

---

## 9. Mecanismo de impersonación de platform_owner: `tenant_id` del token no se usa en la app, y `read_only_impersonation` no se valida

**Archivo(s):**
- `backend/app/api/platform.py:508-527` — `impersonate_tenant`. Emite un
  JWT con:
  ```python
  access_token = create_access_token(
      data={
          "sub": str(current_user.id),
          "tenant_id": str(tenant_id),
          "read_only_impersonation": True,
      },
      expires_at=expires_at,
  )
  ```
- `backend/app/api/auth.py:86-111` — `get_current_user`. Solo lee `sub`
  del token (línea 100), carga el `User` de BD (línea 108) y lo retorna.
  El claim `tenant_id` del token **se ignora por completo** —
  `current_user.tenant_id` siempre es el tenant propio del usuario en BD
  (columna `users.tenant_id`), nunca el tenant impersonado.
- `backend/app/middleware/tenant_context.py:71-74` — SÍ lee el claim
  `tenant_id` del token:
  ```python
  tid = payload.get("tenant_id")
  if tid:
      # Preferred path: tenant_id embedded in token.
      tenant_id = str(UUID(tid))
  ```
  pero únicamente para setear `request.state.tenant_id`, que alimenta
  `app.current_tenant_id` de RLS a nivel Postgres — no toca nada de la
  lógica de aplicación.
- `read_only_impersonation` aparece **una sola vez en todo el backend**
  (`platform.py:524`, donde se crea el claim) — no se valida en ningún
  otro lugar del código.

**Problema:** hay dos capas leyendo el mismo JWT de impersonación de forma
divergente. RLS (vía el middleware) sí reposiciona el contexto de tenant a
nivel de base de datos usando el `tenant_id` del token. Pero la capa de
aplicación (`get_current_user`, y por extensión cualquier endpoint que
filtre explícitamente por `current_user.tenant_id`, que es el patrón
dominante en este código) sigue usando el tenant propio del
`platform_owner`, no el tenant impersonado — el claim se emite pero nunca
se consume ahí. Además, el claim `read_only_impersonation: True` es
puramente decorativo: no existe ningún middleware o dependency que
bloquee métodos no-GET cuando ese claim está presente, así que la promesa
de "solo lectura" no se aplica en ningún punto del código.

**Nota — esto es un problema de ARQUITECTURA del mecanismo completo, no de
un endpoint puntual.** No es específico de billing, finance o
industry_onboarding (los módulos auditados en hallazgos recientes) — afecta
potencialmente cualquier endpoint que la impersonación debería alcanzar,
porque el mismatch está en `get_current_user`, que es la dependency que
usa prácticamente toda la API.

**Nota sobre el efecto práctico probable hoy (hipótesis razonada a partir
del código, NO confirmada con un test real — no se escribió ese test
end-to-end en este hallazgo):** un `platform_owner` que impersona un
tenant probablemente ve datos vacíos o `404` en los endpoints que filtran
por `current_user.tenant_id` explícito (porque ese sigue siendo el tenant
propio del `platform_owner`, no el impersonado) — no una fuga de datos
hacia el tenant ajeno. Es más un problema de "la funcionalidad de
impersonar probablemente no funciona como se espera" que de exposición de
datos, pero queda como hipótesis a validar, no como hecho confirmado.

**Fix sugerido (no implementar ahora) — preguntas de diseño abiertas, no
una solución cerrada:**
- ¿`get_current_user` debería resolver `current_user.tenant_id` desde el
  claim `tenant_id` del token cuando existe, haciendo que impersonar de
  verdad cambie el contexto de aplicación (no solo el de RLS)?
- ¿`read_only_impersonation` debería aplicarse en un middleware/dependency
  que bloquee métodos no-GET cuando el claim está presente, para que la
  promesa de "solo lectura" sea real?
- ¿Es deseable que un `platform_owner` impersonando termine operando con
  un `User` en memoria cuyo `tenant_id` no coincide con su fila real en
  BD? Eso tiene implicaciones en auditoría/logging (¿qué tenant_id se
  registra en los logs de acciones?) que también habría que decidir.

**Riesgo si no se corrige:** alto — no por fuga de datos (que no está
confirmada), sino porque es la base de cualquier flujo de soporte de
`platform_owner` sobre tenants ajenos, y hoy parece no funcionar de forma
consistente entre la capa de RLS y la capa de aplicación.

**✅ RESUELTO** (2026-08-23): decisión de diseño tomada — override en
memoria de `tenant_id` sobre el `User` que devuelve `get_current_user`
(nunca persistido: sin `flush`/`commit` en esa función, sin
`session.merge()`) cuando el claim `tenant_id` del token difiere del de
la fila en BD, más un middleware nuevo (`ImpersonationReadOnlyMiddleware`,
`app/middleware/impersonation_guard.py`) que bloquea con 403 cualquier
método no-GET/HEAD/OPTIONS cuando el token trae
`read_only_impersonation: True`, registrado junto a
`TenantContextMiddleware`/`TrialGuardMiddleware` en `app/main.py`.
`tenant_context.py` no se tocó (ya funcionaba correctamente). Verificado
end-to-end con `scripts/diagnostics/test_impersonation.py` contra la BD
real: token de impersonación ve los datos del tenant objetivo (no los del
`platform_owner`), un POST con ese token devuelve 403 sin crear nada, y
un POST con token normal (sin impersonación) sigue funcionando igual que
antes — 4/4 PASS.

**Hallazgo nuevo encontrado durante la implementación (no confirmado como
explotado, candidato a hallazgo #10, evaluar antes de tocar):** el
override en memoria de `user.tenant_id` marca ese objeto ORM como "dirty"
en SQLAlchemy — asignar un atributo sobre un objeto ya persistente en la
sesión lo marca dirty automáticamente, sin necesidad de `session.merge()`
ni `db.add()` explícito. Si en la MISMA request ocurre un `db.commit()`
más adelante (aunque sea un commit incidental, no relacionado con
`current_user`), ese commit haría flush de TODO el unit-of-work de la
sesión, incluyendo el `tenant_id` sobreescrito — lo que persistiría en
BD el tenant_id impersonado sobre la fila real del `platform_owner`. El
guardrail de solo-lectura (bloquear métodos no-GET) reduce mucho la
superficie pero no la cierra del todo: ya existe un caso real de un GET
que hace commit incidental — `agents.py::list_suggestions` marca
sugerencias vencidas como `"expired"` y llama `db.commit()` dentro de un
handler GET. Si ese endpoint (u otro GET con un patrón similar) se
alcanza durante una sesión de impersonación, el `tenant_id` en memoria
del `platform_owner` quedaría persistido por error. No se corrigió acá
— queda para evaluar en el chat (opciones: `db.expunge(user)` después del
override, o revisar cada GET que haga commit incidental).

**✅ RESUELTO** (2026-08-23): se implementó `db.expunge(user)` en
`get_current_user` inmediatamente después de sobreescribir
`user.tenant_id`, dentro de la misma rama condicional (solo cuando hay
impersonación activa) — desprende el objeto de la sesión para que ningún
`db.commit()` posterior en la misma request, sin importar dónde ocurra,
pueda arrastrar el `tenant_id` sobreescrito a BD. Cubierto por el punto
f) nuevo de `scripts/diagnostics/test_impersonation.py`, que reproduce
exactamente el escenario descrito arriba contra la BD real: crea una
sugerencia ya vencida en el tenant objetivo, llama
`GET /api/agents/suggestions` con el token de impersonación (confirmando
que el commit interno de `list_suggestions` sí corrió — la sugerencia
queda `"expired"`), y verifica con una consulta directa a BD, en una
sesión aparte, que la fila real del `platform_owner` en `users` conserva
su `tenant_id` original — PASS.

---

## Resumen para priorizar

| # | Hallazgo | Archivo(s) | Riesgo | Esfuerzo estimado | Estado |
|---|---|---|---|---|---|
| 1 | `_MULTI_BRANCH_ROLES` divergente | leads.py, pipeline.py, pipelines.py, users.py, metrics.py | Bajo-medio | Chico | **✅ Resuelto (2026-08-22)** |
| 2 | `users.py::_require_owner` sin PLATFORM_OWNER | users.py | Bajo | Chico | **✅ Resuelto (2026-08-23)** |
| 3 | `industry_onboarding.py::_OWNER_ROLES` = (OWNER,) | industry_onboarding.py | Bajo | Chico | **✅ Resuelto (2026-08-23)** |
| 4 | `automations.py::_OWNER_PLUS` vs `_OWNER_TIER` | automations.py, actions_catalog.py | Bajo | Mediano (requiere decisión de producto, no solo código) | **✅ Resuelto (2026-08-23)** |
| 5 | `delete_deal` sin restricción de rol | deals.py | **Alto** | Chico | **✅ Resuelto (2026-08-20)** |
| 6 | `set_monthly_goal` duplicado (Copiloto vs REST) | copilot_tools.py, goals.py | Bajo | Mediano (requiere decisión de arquitectura) | **✅ Resuelto (2026-08-23)** |
| 7 | `confirm_suggestion`/`dismiss_suggestion` sin ownership | agents.py | Medio | Chico | **✅ Resuelto (2026-08-23)** |
| 8 | Tools de finanzas del Copiloto sin `FinancePermission` | copilot_tools.py, finance_access.py | **Alto** | Chico | **✅ Resuelto (2026-08-21)** |
| 9 | Impersonación: tenant_id del token no se usa en la app | auth.py, platform.py, tenant_context.py | **Alto** | Grande (rediseño de arquitectura, no un fix mecánico) | **✅ Resuelto (2026-08-23)** |
