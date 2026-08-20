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

---

## Resumen para priorizar

| # | Hallazgo | Archivo(s) | Riesgo | Esfuerzo estimado |
|---|---|---|---|---|
| 1 | `_MULTI_BRANCH_ROLES` divergente | leads.py, pipeline.py, pipelines.py, users.py, metrics.py | Bajo-medio | Chico |
| 2 | `users.py::_require_owner` sin PLATFORM_OWNER | users.py | Bajo | Chico |
| 3 | `industry_onboarding.py::_OWNER_ROLES` = (OWNER,) | industry_onboarding.py | Bajo | Chico |
| 4 | `automations.py::_OWNER_PLUS` vs `_OWNER_TIER` | automations.py, actions_catalog.py | Bajo | Mediano (requiere decisión de producto, no solo código) |
| 5 | `delete_deal` sin restricción de rol | deals.py | **Alto** | Chico |
| 6 | `set_monthly_goal` duplicado (Copiloto vs REST) | copilot_tools.py, goals.py | Bajo | Mediano (requiere decisión de arquitectura) |
| 7 | `confirm_suggestion`/`dismiss_suggestion` sin ownership | agents.py | Medio | Chico |
