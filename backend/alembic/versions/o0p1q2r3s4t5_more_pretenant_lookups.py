"""Lookups pre-tenant adicionales: meta_lead_configs por page_id, users por wa_phone

Revision ID: o0p1q2r3s4t5
Revises: n9o0p1q2r3s4
Create Date: 2026-08-15

Mismo patrón de Parte 1 (lookup puntual, no barrido cruza-tenant) para dos
casos encontrados auditando Grupo D:

  a) app/api/webhooks.py — el webhook de Meta Lead Ads busca
     MetaLeadConfig por page_id (identificador externo de Meta) ANTES de
     conocer el tenant — igual que wa_phone_number_id en el webhook de
     WhatsApp (Parte 1). A diferencia de fn_lookup_tenant_by_email (que solo
     devuelve tenant_id), acá hace falta la fila casi completa
     (branch_id, tenant_id, form_ids, page_access_token, field_mapping)
     porque el código tiene que decidir CUÁL config coincide por form_id
     DESPUÉS de resolver el page_id — no hay forma de hacer "resolver
     tenant_id, después releer con contexto" en dos pasos limpios como en
     los demás casos, porque distintos tenants podrían (en teoría) compartir
     un page_id y la desambiguación final es por form_id, no por tenant.
     Esto NO amplía lo que el código ya leía hoy vía ORM sin ninguna
     restricción de tenant — solo lo hace funcionar bajo RLS real.

  b) app/api/internal_wa.py — busca User por wa_phone (canal de WhatsApp
     interno de Walix, cualquier empleado de cualquier tenant puede
     escribir) ANTES de conocer el tenant — igual que login por email.
     fn_lookup_tenant_by_user_wa_phone sigue el patrón simple de
     Parte 1 (solo devuelve tenant_id).

     A diferencia de fn_lookup_tenant_by_email (que puede confiar en
     ix_users_email, UNIQUE), users.wa_phone NO tiene ningún constraint de
     unicidad (ni global ni compuesto con tenant_id — verificado contra
     app/models/user.py y el catálogo real de Postgres: pg_constraint /
     pg_indexes sobre `users` solo tiene UNIQUE en id y email). Un LIMIT 1
     silencioso ahí elegiría un tenant arbitrario si dos Users activos
     (de cualquier tenant) llegaran a compartir wa_phone — inaceptable para
     un canal que enruta comandos e información real de un tenant. La
     función ahora cuenta las coincidencias activas primero y hace
     RAISE EXCEPTION (SQLSTATE 23505, unique_violation) si hay más de una,
     en vez de devolver cualquiera de ellas. app/api/internal_wa.py captura
     ese IntegrityError específicamente (en el helper
     _resolve_tenant_by_wa_phone), lo loguea como dato inconsistente que
     requiere revisión manual, y responde al usuario como si el teléfono no
     estuviera reconocido — nunca enruta a un tenant al azar.

     DECISIÓN CONFIRMADA (no es un caso ambiguo a interpretar): un mismo
     wa_phone en más de un User activo — mismo tenant o tenants distintos —
     es SIEMPRE un error de datos. No existe ningún escenario de "un mismo
     empleado trabajando para 2 clínicas" a soportar para la tabla `users`.
     (Nota aparte, sin relación: la unicidad de wa_phone de LEADS sí permite
     que un mismo cliente exista en 2 tenants — eso ya está resuelto
     correctamente desde Parte 1 vía fn_lookup_tenant_by_wa_phone_id, que
     resuelve el tenant por el número de WhatsApp de NEGOCIO de la
     sucursal, no por el número del cliente. No aplica acá.)
"""
from alembic import op
from sqlalchemy import text

revision = "o0p1q2r3s4t5"
down_revision = "n9o0p1q2r3s4"
branch_labels = None
depends_on = None

_GRANTEE = "walix_app"


def _role_exists(conn, role: str) -> bool:
    return conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r)"), {"r": role}
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("""
        CREATE FUNCTION fn_lookup_meta_lead_configs_by_page_id(p_page_id text)
        RETURNS TABLE(
            id uuid,
            branch_id uuid,
            tenant_id uuid,
            form_ids jsonb,
            page_access_token text,
            field_mapping jsonb
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT id, branch_id, tenant_id, form_ids, page_access_token, field_mapping
            FROM meta_lead_configs
            WHERE page_id = p_page_id AND is_active = TRUE;
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_lookup_meta_lead_configs_by_page_id(text) FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_lookup_meta_lead_configs_by_page_id(text) IS
        'Resuelve MetaLeadConfig por page_id de Meta SIN pasar por RLS
        (SECURITY DEFINER) — usado por el webhook de Meta Lead Ads en
        app/api/webhooks.py, que busca la config ANTES de conocer el
        tenant. Devuelve las mismas columnas que el ORM ya leía sin
        restricción de tenant (incluye page_access_token, cifrado a nivel
        de aplicación antes de guardarse). GRANT EXECUTE limitado a
        walix_app — ver migración o0p1q2r3s4t5.'
    """))

    conn.execute(text("""
        CREATE FUNCTION fn_lookup_tenant_by_user_wa_phone(p_wa_phone text)
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
            v_count integer;
            v_tenant_id uuid;
        BEGIN
            -- max(uuid) no existe en Postgres estándar (sin extensión) —
            -- array_agg()[1] logra el mismo "una sola pasada" sin depender
            -- de un agregado que no está definido para uuid. Cuál de los
            -- valores termina en la posición 1 es irrelevante: solo se usa
            -- cuando v_count <= 1 (determinístico o NULL); con v_count > 1
            -- se hace RAISE EXCEPTION antes de leer v_tenant_id.
            SELECT count(*), (array_agg(tenant_id))[1] INTO v_count, v_tenant_id
            FROM users
            WHERE wa_phone = p_wa_phone AND is_active = TRUE;

            IF v_count > 1 THEN
                RAISE EXCEPTION
                    'wa_phone "%" matches % active users (expected 0 or 1) — inconsistent data, needs manual review',
                    p_wa_phone, v_count
                    USING ERRCODE = '23505';
            END IF;

            RETURN v_tenant_id; -- NULL si v_count = 0, el tenant si v_count = 1
        END;
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_lookup_tenant_by_user_wa_phone(text) FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_lookup_tenant_by_user_wa_phone(text) IS
        'Resuelve tenant_id por wa_phone de un User SIN pasar por RLS
        (SECURITY DEFINER) — usado por app/api/internal_wa.py (canal de
        WhatsApp interno de Walix), que busca el usuario por su teléfono
        ANTES de conocer el tenant. Devuelve SOLO tenant_id (NULL si no hay
        ningún User activo con ese wa_phone). users.wa_phone NO tiene
        constraint de unicidad (ver docstring de esta migración). DECISIÓN
        CONFIRMADA: un mismo wa_phone en más de un User activo — del mismo
        tenant o de tenants distintos — es SIEMPRE un error de datos, nunca
        un caso legítimo a soportar (no existe el escenario de "un empleado
        trabajando para 2 clínicas" para esta tabla). Por eso la función
        RAISE EXCEPTION (SQLSTATE 23505) si hay más de un match, en vez de
        elegir uno arbitrario con LIMIT 1. GRANT EXECUTE limitado a
        walix_app — ver migración o0p1q2r3s4t5.'
    """))

    if _role_exists(conn, _GRANTEE):
        conn.execute(text(
            f"GRANT EXECUTE ON FUNCTION fn_lookup_meta_lead_configs_by_page_id(text) TO {_GRANTEE}"
        ))
        conn.execute(text(
            f"GRANT EXECUTE ON FUNCTION fn_lookup_tenant_by_user_wa_phone(text) TO {_GRANTEE}"
        ))
    else:
        print(
            f"[o0p1q2r3s4t5] AVISO: el rol '{_GRANTEE}' no existe todavía en este entorno — "
            f"las funciones se crearon pero sin GRANT EXECUTE. Correr scripts/setup_db_user.py y luego:\n"
            f"  GRANT EXECUTE ON FUNCTION fn_lookup_meta_lead_configs_by_page_id(text) TO {_GRANTEE};\n"
            f"  GRANT EXECUTE ON FUNCTION fn_lookup_tenant_by_user_wa_phone(text) TO {_GRANTEE};"
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP FUNCTION IF EXISTS fn_lookup_meta_lead_configs_by_page_id(text)"))
    conn.execute(text("DROP FUNCTION IF EXISTS fn_lookup_tenant_by_user_wa_phone(text)"))
