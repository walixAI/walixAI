"""ai_token_usage — Copiloto Fase 1, Parte C.

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2026-08-18

Tabla de TENANT normal — CON RLS estándar (4 policies), a propósito
OPUESTO a platform_ai_model_config (raíz, sin RLS, migración
r3s4t5u6v7w8): un tenant no debe poder ver el consumo de tokens de otro.

fn_aggregate_token_usage_platform(start_date, end_date) sigue el mismo
patrón de agregación cross-tenant que las fn_platform_* de la migración
p1q2r3s4t5u6 (SECURITY DEFINER, REVOKE ALL FROM PUBLIC, GRANT EXECUTE
condicional a walix_app) — la usará el dashboard de Fase 7 para que
platform_owner vea consumo agregado por tenant sin bypassear RLS de
ninguna otra manera. Devuelve solo sumas numéricas y tenant_name (de
`tenants`, que no tiene RLS) — nunca contenido de conversaciones.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "s4t5u6v7w8x9"
down_revision = "r3s4t5u6v7w8"
branch_labels = None
depends_on = None

_GRANTEE = "walix_app"
_TABLE = "ai_token_usage"
_FUNCTION_SIG = "fn_aggregate_token_usage_platform(timestamptz, timestamptz)"


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Tabla ─────────────────────────────────────────────────────────────
    op.create_table(
        _TABLE,
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("model_used", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_token_usage_tenant_id", _TABLE, ["tenant_id"])
    op.create_index("ix_ai_token_usage_branch_id", _TABLE, ["branch_id"])
    op.create_index("ix_ai_token_usage_source", _TABLE, ["source"])
    op.create_index("ix_ai_token_usage_created_at", _TABLE, ["created_at"])

    # ── 2. RLS estándar (mismo patrón que p1q2r3s4t5u6) ─────────────────────
    conn.execute(text(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY"))
    conn.execute(text(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY"))

    conn.execute(text(f"""
        CREATE POLICY tenant_isolation_select ON {_TABLE}
          FOR SELECT USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
          )
    """))
    conn.execute(text(f"""
        CREATE POLICY tenant_isolation_insert ON {_TABLE}
          FOR INSERT WITH CHECK (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
          )
    """))
    conn.execute(text(f"""
        CREATE POLICY tenant_isolation_update ON {_TABLE}
          FOR UPDATE USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
          )
    """))
    conn.execute(text(f"""
        CREATE POLICY tenant_isolation_delete ON {_TABLE}
          FOR DELETE USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
          )
    """))

    # ── 3. Agregación cross-tenant para el dashboard de Fase 7 ─────────────
    conn.execute(text("""
        CREATE FUNCTION fn_aggregate_token_usage_platform(p_from timestamptz, p_to timestamptz)
        RETURNS TABLE(
            tenant_id uuid,
            tenant_name text,
            total_input_tokens bigint,
            total_output_tokens bigint,
            total_cost_usd numeric
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT
                u.tenant_id,
                t.name,
                coalesce(sum(u.input_tokens), 0),
                coalesce(sum(u.output_tokens), 0),
                coalesce(sum(u.estimated_cost_usd), 0)
            FROM ai_token_usage u
            JOIN tenants t ON t.id = u.tenant_id
            WHERE u.created_at >= p_from
              AND u.created_at <= p_to
            GROUP BY u.tenant_id, t.name;
        $$
    """))
    conn.execute(text(f"REVOKE ALL ON FUNCTION {_FUNCTION_SIG} FROM PUBLIC"))
    conn.execute(text(f"""
        COMMENT ON FUNCTION {_FUNCTION_SIG} IS
        'Suma input_tokens/output_tokens/estimated_cost_usd de ai_token_usage
        por tenant en un rango de fechas, cruzando tenants a propósito — para
        el dashboard de Platform Owner (Fase 7 del plan de copiloto). Solo
        agregados numéricos y tenant_name (de tenants, sin RLS) — nunca
        contenido de conversaciones ni filas individuales. GRANT EXECUTE
        limitado a walix_app — ver migración s4t5u6v7w8x9.'
    """))

    # GRANT condicional resuelto en SQL, no en Python — ver comentario
    # equivalente en la migración p1q2r3s4t5u6 (mismo hallazgo, mismo fix):
    # un `if _role_exists(...)` Python-side rompe `alembic upgrade ... --sql`
    # porque op.get_bind() en modo offline devuelve una conexión simulada
    # cuyo .execute(...) es None — `.scalar()` sobre None revienta el
    # dry-run. El bloque DO corre entero en Postgres en tiempo de ejecución,
    # así que es válido tanto online como impreso tal cual en --sql.
    conn.execute(text(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_GRANTEE}') THEN
                EXECUTE 'GRANT EXECUTE ON FUNCTION {_FUNCTION_SIG} TO {_GRANTEE}';
            ELSE
                RAISE NOTICE '[s4t5u6v7w8x9] rol % no existe todavía en este entorno — función creada sin GRANT EXECUTE. Correr scripts/setup_db_user.py.', '{_GRANTEE}';
            END IF;
        END
        $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(text(f"DROP FUNCTION IF EXISTS {_FUNCTION_SIG}"))

    conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation_select ON {_TABLE}"))
    conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation_insert ON {_TABLE}"))
    conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation_update ON {_TABLE}"))
    conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation_delete ON {_TABLE}"))
    conn.execute(text(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_ai_token_usage_created_at", table_name=_TABLE)
    op.drop_index("ix_ai_token_usage_source", table_name=_TABLE)
    op.drop_index("ix_ai_token_usage_branch_id", table_name=_TABLE)
    op.drop_index("ix_ai_token_usage_tenant_id", table_name=_TABLE)
    op.drop_table(_TABLE)
