"""RLS en las 5 tablas pendientes: ai_memory_events, ai_entity_context,
expenses, subscriptions, failed_payments — y arreglo del gap encontrado en
app/api/platform.py durante la auditoría de esta migración.

Revision ID: p1q2r3s4t5u6
Revises: o0p1q2r3s4t5
Create Date: 2026-08-17

CONTEXTO: walix_app ya es el rol runtime real en producción (cutover
cerrado, commit 832e6af). A diferencia del resto de la serie, activar
FORCE ROW LEVEL SECURITY acá es un cambio con efecto inmediato: cualquier
call-site que no fije app.current_tenant_id antes de tocar estas tablas
pasa a ver 0 filas, sin excepción — no un error ruidoso. Por eso esta
migración se auditó primero (Paso 1, sin escribir código) y agrupa TODO lo
que esa auditoría encontró, no solo el ALTER TABLE de las 5 tablas.

AUDITORÍA — resumen de los 3 casos especiales encontrados:

1) app/tasks/ai_memory_tasks.py — update_entity_context_task hace
   `db.get(AIMemoryEvent, id)` para descubrir el tenant_id ANTES de poder
   llamar set_tenant_context (necesita leer la fila para saber a qué
   tenant pertenece). Caso pre-tenant idéntico en forma a
   fn_lookup_tenant_by_email — fn_lookup_ai_memory_event_tenant() resuelve
   SOLO el tenant_id; el código sigue haciendo el db.get() normal después,
   ya bajo el tenant correcto.

2) app/tasks/finance_tasks.py::run_generate_recurring_expenses — barrido
   cross-tenant PERMANENTE (Celery beat, día 1 de cada mes), no un caso
   pre-tenant: procesa RecurringExpense de TODOS los tenants en una sola
   pasada. recurring_expenses no tiene RLS (fuera de alcance de esta
   migración), así que enumerar las plantillas no requiere función nueva
   — el problema es que expense_generation.py::generate_recurring_expenses
   nunca llamaba set_tenant_context antes de leer/escribir `expenses` (una
   de las 5 tablas de hoy). Con FORCE RLS, el SELECT de idempotencia
   (¿ya se generó este mes?) siempre devolvería 0 filas y el INSERT
   subsiguiente violaría el WITH CHECK — el job fallaría el día 1 de cada
   mes sin generar nada para nadie. Arreglado en código (no requiere
   función SECURITY DEFINER): la función ahora agrupa las plantillas por
   tenant_id y llama set_tenant_context() una vez por tenant antes de
   tocar `expenses` para ese tenant.

3) app/api/billing_webhook.py — los 4 handlers de eventos de Stripe (sin
   JWT, resuelven tenant desde el payload de Stripe) nunca llamaban
   set_tenant_context antes de tocar `subscriptions`/`failed_payments`.
   NO hace falta ninguna función SECURITY DEFINER nueva acá: `tenants` no
   tiene RLS (es la raíz del modelo de aislamiento, nunca se protegió a
   sí misma — confirmado, ninguna migración previa la toca), así que cada
   handler puede resolver tenant_id primero vía Tenant.stripe_customer_id
   (dato que Stripe siempre manda) o directo de metadata.tenant_id (ya lo
   hacía _handle_checkout_completed), y recién ahí llamar
   set_tenant_context antes de cualquier query sobre las tablas de hoy.

HALLAZGO FUERA DE ALCANCE ORIGINAL, incluido por decisión del usuario:
app/api/platform.py (dashboard interno, role=platform_owner) hace
agregaciones cross-tenant sobre leads/messages/conversations/branches/
ai_command_logs — tablas que YA tienen RLS desde el cutover original — sin
llamar set_tenant_context en ningún lado del archivo. Es decir, antes de
esta migración el dashboard de Platform Owner ya estaba devolviendo datos
vacíos/en $0 para leads, costos de IA y (una vez viva esta migración)
también para subscriptions/failed_payments. Se agregan funciones
SECURITY DEFINER de AGREGACIÓN (no lookup puntual, primera vez en la serie
que se necesita este tipo) para los 3 patrones que el archivo usa:
  - fn_platform_lead_counts_by_tenant()
  - fn_platform_message_tokens_by_tenant(from, to)
  - fn_platform_command_tokens_by_tenant(from, to)
  - fn_platform_list_active_subscription_plans()
  - fn_platform_count_failed_payments_since(since)
Todas devuelven agregados (conteos/sumas), nunca filas completas de datos
de un tenant individual — el mismo principio de mínimo privilegio que el
resto de la serie, adaptado a "agregación" en vez de "lookup puntual" o
"enumeración de existencia". app/api/platform.py::get_tenant_detail
(endpoint de detalle de UN tenant conocido por path param) no necesita
función nueva — alcanza con set_tenant_context(db, tenant_id) apenas se
conoce el tenant_id, igual que cualquier endpoint estándar.
"""
from alembic import op
from sqlalchemy import text

revision = "p1q2r3s4t5u6"
down_revision = "o0p1q2r3s4t5"
branch_labels = None
depends_on = None

_GRANTEE = "walix_app"

_RLS_TABLES = (
    "ai_memory_events",
    "ai_entity_context",
    "expenses",
    "subscriptions",
    "failed_payments",
)

_NEW_FUNCTIONS_NO_ARGS = (
    "fn_lookup_ai_memory_event_tenant(uuid)",
    "fn_platform_lead_counts_by_tenant()",
    "fn_platform_message_tokens_by_tenant(timestamptz, timestamptz)",
    "fn_platform_command_tokens_by_tenant(timestamptz, timestamptz)",
    "fn_platform_list_active_subscription_plans()",
    "fn_platform_count_failed_payments_since(timestamptz)",
)


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. RLS + policies en las 5 tablas ───────────────────────────────────
    for table in _RLS_TABLES:
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))

        conn.execute(text(f"""
            CREATE POLICY tenant_isolation_select ON {table}
              FOR SELECT USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
              )
        """))
        conn.execute(text(f"""
            CREATE POLICY tenant_isolation_insert ON {table}
              FOR INSERT WITH CHECK (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
              )
        """))
        conn.execute(text(f"""
            CREATE POLICY tenant_isolation_update ON {table}
              FOR UPDATE USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
              )
        """))
        conn.execute(text(f"""
            CREATE POLICY tenant_isolation_delete ON {table}
              FOR DELETE USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
              )
        """))

    # ── 2. Pre-tenant lookup: ai_memory_events por id ───────────────────────
    conn.execute(text("""
        CREATE FUNCTION fn_lookup_ai_memory_event_tenant(p_event_id uuid)
        RETURNS uuid
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT tenant_id FROM ai_memory_events WHERE id = p_event_id;
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_lookup_ai_memory_event_tenant(uuid) FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_lookup_ai_memory_event_tenant(uuid) IS
        'Resuelve tenant_id de un AIMemoryEvent por id SIN pasar por RLS
        (SECURITY DEFINER) — usado por
        app/tasks/ai_memory_tasks.py::update_entity_context_task, que
        necesita leer la fila para descubrir su tenant ANTES de poder
        llamar set_tenant_context. Devuelve SOLO tenant_id; el caller
        vuelve a hacer db.get(AIMemoryEvent, id) normal después, ya bajo
        el tenant context correcto. GRANT EXECUTE limitado a walix_app —
        ver migración p1q2r3s4t5u6.'
    """))

    # ── 3. Agregaciones cross-tenant para app/api/platform.py ──────────────
    conn.execute(text("""
        CREATE FUNCTION fn_platform_lead_counts_by_tenant()
        RETURNS TABLE(tenant_id uuid, lead_count bigint)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT tenant_id, count(*) FROM leads GROUP BY tenant_id;
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_platform_lead_counts_by_tenant() FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_platform_lead_counts_by_tenant() IS
        'Cuenta leads de TODOS los tenants agrupado por tenant_id, cruzando
        tenants a propósito — usado por GET /api/platform/tenants (dashboard
        de Platform Owner). Solo agregados (conteos), nunca filas de leads.
        GRANT EXECUTE limitado a walix_app — ver migración p1q2r3s4t5u6.'
    """))

    conn.execute(text("""
        CREATE FUNCTION fn_platform_message_tokens_by_tenant(p_from timestamptz, p_to timestamptz)
        RETURNS TABLE(tenant_id uuid, tokens bigint)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT b.tenant_id, coalesce(sum(m.tokens_used), 0)
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            JOIN branches b ON c.branch_id = b.id
            WHERE m.created_at >= p_from
              AND m.created_at <= p_to
              AND m.tokens_used IS NOT NULL
            GROUP BY b.tenant_id;
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_platform_message_tokens_by_tenant(timestamptz, timestamptz) FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_platform_message_tokens_by_tenant(timestamptz, timestamptz) IS
        'Suma tokens_used de messages por tenant (vía conversations→branches)
        en un rango de fechas, cruzando tenants a propósito — usado por
        app/api/platform.py::_ai_tokens_by_tenant (dashboard de Platform
        Owner: /stats, /tenants, /ai-costs). Solo agregados, nunca filas de
        mensajes. GRANT EXECUTE limitado a walix_app — ver migración
        p1q2r3s4t5u6.'
    """))

    conn.execute(text("""
        CREATE FUNCTION fn_platform_command_tokens_by_tenant(p_from timestamptz, p_to timestamptz)
        RETURNS TABLE(tenant_id uuid, tokens bigint)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT tenant_id, coalesce(sum(tokens_used), 0)
            FROM ai_command_logs
            WHERE created_at >= p_from
              AND created_at <= p_to
              AND tokens_used IS NOT NULL
            GROUP BY tenant_id;
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_platform_command_tokens_by_tenant(timestamptz, timestamptz) FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_platform_command_tokens_by_tenant(timestamptz, timestamptz) IS
        'Suma tokens_used de ai_command_logs por tenant en un rango de
        fechas, cruzando tenants a propósito — usado por
        app/api/platform.py::_ai_tokens_by_tenant (dashboard de Platform
        Owner: /stats, /tenants, /ai-costs). Solo agregados, nunca filas de
        comandos. GRANT EXECUTE limitado a walix_app — ver migración
        p1q2r3s4t5u6.'
    """))

    conn.execute(text("""
        CREATE FUNCTION fn_platform_list_active_subscription_plans()
        RETURNS TABLE(plan text)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT plan FROM subscriptions WHERE status = 'active';
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_platform_list_active_subscription_plans() FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_platform_list_active_subscription_plans() IS
        'Lista el plan de cada Subscription activa de TODOS los tenants,
        cruzando tenants a propósito — usado por GET /api/platform/stats
        (dashboard de Platform Owner) para calcular stripe_mrr_mxn. Devuelve
        SOLO la columna plan, nunca datos de facturación o del cliente de
        Stripe. GRANT EXECUTE limitado a walix_app — ver migración
        p1q2r3s4t5u6.'
    """))

    conn.execute(text("""
        CREATE FUNCTION fn_platform_count_failed_payments_since(p_since timestamptz)
        RETURNS bigint
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT count(*) FROM failed_payments WHERE created_at >= p_since;
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_platform_count_failed_payments_since(timestamptz) FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_platform_count_failed_payments_since(timestamptz) IS
        'Cuenta FailedPayment desde una fecha, de TODOS los tenants, cruzando
        tenants a propósito — usado por GET /api/platform/stats (dashboard
        de Platform Owner). Solo el conteo, nunca los detalles de cada pago
        fallido. GRANT EXECUTE limitado a walix_app — ver migración
        p1q2r3s4t5u6.'
    """))

    # GRANT condicional resuelto en SQL, no en Python — un `if _role_exists(...)`
    # Python-side necesita conn.execute(...).scalar() con un resultado REAL,
    # que solo existe en modo online. En modo `alembic upgrade ... --sql`
    # (offline), op.get_bind() da una conexión simulada que solo imprime SQL:
    # conn.execute(...) devuelve None y `.scalar()` revienta el dry-run
    # (AttributeError). No afectó la aplicación real a producción — el rol ya
    # existía y el upgrade corrió en modo online, donde .scalar() sí resuelve
    # — pero rompe cualquier intento de generar el SQL con --sql. El bloque
    # DO de abajo corre entero dentro de Postgres (chequea pg_roles en tiempo
    # de EJECUCIÓN, no de generación), así que es válido tanto online como
    # impreso tal cual en modo --sql. Ver hallazgo 2026-08-18 en s4t5u6v7w8x9.
    _grant_stmts = "\n                ".join(
        f"EXECUTE 'GRANT EXECUTE ON FUNCTION {fn} TO {_GRANTEE}';" for fn in _NEW_FUNCTIONS_NO_ARGS
    )
    conn.execute(text(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_GRANTEE}') THEN
                {_grant_stmts}
            ELSE
                RAISE NOTICE '[p1q2r3s4t5u6] rol % no existe todavía en este entorno — funciones creadas sin GRANT EXECUTE. Correr scripts/setup_db_user.py.', '{_GRANTEE}';
            END IF;
        END
        $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("DROP FUNCTION IF EXISTS fn_platform_count_failed_payments_since(timestamptz)"))
    conn.execute(text("DROP FUNCTION IF EXISTS fn_platform_list_active_subscription_plans()"))
    conn.execute(text("DROP FUNCTION IF EXISTS fn_platform_command_tokens_by_tenant(timestamptz, timestamptz)"))
    conn.execute(text("DROP FUNCTION IF EXISTS fn_platform_message_tokens_by_tenant(timestamptz, timestamptz)"))
    conn.execute(text("DROP FUNCTION IF EXISTS fn_platform_lead_counts_by_tenant()"))
    conn.execute(text("DROP FUNCTION IF EXISTS fn_lookup_ai_memory_event_tenant(uuid)"))

    for table in _RLS_TABLES:
        conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation_select ON {table}"))
        conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation_insert ON {table}"))
        conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation_update ON {table}"))
        conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation_delete ON {table}"))
        conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
