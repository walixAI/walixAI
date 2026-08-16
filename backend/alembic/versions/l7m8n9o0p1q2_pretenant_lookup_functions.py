"""Lookups pre-tenant seguros: fn_lookup_tenant_by_email, fn_lookup_tenant_by_wa_phone_id

Revision ID: l7m8n9o0p1q2
Revises: k6l7m8n9o0p1
Create Date: 2026-08-15

CONTEXTO: login (app/api/auth.py) y el webhook de WhatsApp (app/api/webhooks.py)
necesitan buscar una fila (User por email, Branch por wa_phone_number_id) ANTES
de conocer el tenant_id — es la única forma de averiguarlo. Bajo RLS real
(rol walix_app, sin BYPASSRLS), esas queries nunca devuelven filas: la policy
compara contra app.current_tenant_id, que en ese punto del flujo todavía no
está seteado. No es un descuido del filtro de aplicación — es información que
legítimamente no existe todavía.

DISEÑO: dos funciones SQL SECURITY DEFINER, alcance mínimo a propósito:
  - Devuelven SOLO tenant_id (uuid) — nunca la fila completa, nunca
    hashed_password ni ninguna otra columna.
  - SECURITY DEFINER + dueño = rol que corre esta migración (admin/superuser,
    vía effective_alembic_database_url) → corren SIN RLS, sin importar qué
    rol las invoque.
  - SET search_path = public fijo, para blindar contra search_path hijacking
    (el riesgo clásico de seguridad de SECURITY DEFINER en Postgres: si no se
    fija, un rol con privilegios de CREATE en algún schema del search_path
    del invocador podría inyectar una función/tabla que la definer ejecute
    con SUS privilegios elevados).
  - REVOKE de PUBLIC + GRANT EXECUTE solo a walix_app: ningún otro rol puede
    invocarlas, y si otro rol futuro necesita usarlas se vuelve una decisión
    explícita, no un default abierto.
  - GRANT es condicional a que el rol walix_app YA exista en este entorno —
    en un Postgres fresco (CI, un dev nuevo que corre `alembic upgrade head`
    antes de correr scripts/setup_db_user.py) el rol todavía no existe, y un
    GRANT a un rol inexistente rompe la migración entera con un error duro.
    Mismo patrón defensivo que _table_exists() en h4i5j6k7l8m9: no asumir
    que la infraestructura ya está lista, saltear con una advertencia si no.
"""
from alembic import op
from sqlalchemy import text

revision = "l7m8n9o0p1q2"
down_revision = "k6l7m8n9o0p1"
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
        CREATE FUNCTION fn_lookup_tenant_by_email(p_email text)
        RETURNS uuid
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT tenant_id FROM users WHERE email = p_email LIMIT 1;
        $$
    """))
    conn.execute(text("REVOKE ALL ON FUNCTION fn_lookup_tenant_by_email(text) FROM PUBLIC"))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_lookup_tenant_by_email(text) IS
        'Resuelve tenant_id por email SIN pasar por RLS (SECURITY DEFINER) — '
        'usado por login/register/check-email en app/api/auth.py, que buscan '
        'un usuario por email ANTES de conocer su tenant. Devuelve SOLO '
        'tenant_id, nunca hashed_password ni otras columnas. '
        'GRANT EXECUTE limitado a walix_app — ver migración l7m8n9o0p1q2.'
    """))

    conn.execute(text("""
        CREATE FUNCTION fn_lookup_tenant_by_wa_phone_id(p_wa_phone_number_id text)
        RETURNS uuid
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT tenant_id FROM branches WHERE wa_phone_number_id = p_wa_phone_number_id LIMIT 1;
        $$
    """))
    conn.execute(text("REVOKE ALL ON FUNCTION fn_lookup_tenant_by_wa_phone_id(text) FROM PUBLIC"))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_lookup_tenant_by_wa_phone_id(text) IS
        'Resuelve tenant_id por wa_phone_number_id SIN pasar por RLS '
        '(SECURITY DEFINER) — usado por el webhook de WhatsApp en '
        'app/api/webhooks.py, que busca la Branch dueña del número ANTES de '
        'conocer el tenant. Devuelve SOLO tenant_id. '
        'GRANT EXECUTE limitado a walix_app — ver migración l7m8n9o0p1q2.'
    """))

    if _role_exists(conn, _GRANTEE):
        conn.execute(text(
            f"GRANT EXECUTE ON FUNCTION fn_lookup_tenant_by_email(text) TO {_GRANTEE}"
        ))
        conn.execute(text(
            f"GRANT EXECUTE ON FUNCTION fn_lookup_tenant_by_wa_phone_id(text) TO {_GRANTEE}"
        ))
    else:
        print(
            f"[l7m8n9o0p1q2] AVISO: el rol '{_GRANTEE}' no existe todavía en este entorno — "
            f"las funciones se crearon pero sin GRANT EXECUTE. Correr "
            f"scripts/setup_db_user.py y luego:\n"
            f"  GRANT EXECUTE ON FUNCTION fn_lookup_tenant_by_email(text) TO {_GRANTEE};\n"
            f"  GRANT EXECUTE ON FUNCTION fn_lookup_tenant_by_wa_phone_id(text) TO {_GRANTEE};"
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP FUNCTION IF EXISTS fn_lookup_tenant_by_email(text)"))
    conn.execute(text("DROP FUNCTION IF EXISTS fn_lookup_tenant_by_wa_phone_id(text)"))
