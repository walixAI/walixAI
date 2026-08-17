"""Pre-tenant lookup adicional: fn_lookup_tenant_by_stripe_subscription_id

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-08-17

Corrige una regresión introducida en p1q2r3s4t5u6: app/api/billing_webhook.py
::_handle_sub_deleted había quedado reestructurado para resolver tenant_id
vía Tenant.stripe_customer_id (payload de customer.subscription.deleted),
pero ese evento no siempre trae `customer` en el payload que le llega al
handler — el caso real (y el que cubre scripts/test_billing.py, que llama
al handler directo con `{"id": stripe_sub_id}`, sin `customer`) es que una
suscripción a BORRAR siempre existe ya en `subscriptions`, con su propio
tenant_id — no hace falta ningún otro dato del payload de Stripe.

Mismo patrón que fn_lookup_tenant_by_email / fn_lookup_tenant_by_wa_phone_id:
lookup puntual, devuelve SOLO tenant_id.
"""
from alembic import op
from sqlalchemy import text

revision = "q2r3s4t5u6v7"
down_revision = "p1q2r3s4t5u6"
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
        CREATE FUNCTION fn_lookup_tenant_by_stripe_subscription_id(p_stripe_sub_id text)
        RETURNS uuid
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT tenant_id FROM subscriptions WHERE stripe_subscription_id = p_stripe_sub_id;
        $$
    """))
    conn.execute(text(
        "REVOKE ALL ON FUNCTION fn_lookup_tenant_by_stripe_subscription_id(text) FROM PUBLIC"
    ))
    conn.execute(text("""
        COMMENT ON FUNCTION fn_lookup_tenant_by_stripe_subscription_id(text) IS
        'Resuelve tenant_id de una Subscription por stripe_subscription_id SIN
        pasar por RLS (SECURITY DEFINER) — usado por
        app/api/billing_webhook.py::_handle_sub_deleted, que necesita saber
        el tenant ANTES de poder llamar set_tenant_context (el payload de
        customer.subscription.deleted no garantiza traer customer_id). Solo
        se invoca sobre suscripciones que ya existen — nunca crea nada.
        GRANT EXECUTE limitado a walix_app — ver migración q2r3s4t5u6v7.'
    """))

    if _role_exists(conn, _GRANTEE):
        conn.execute(text(
            f"GRANT EXECUTE ON FUNCTION fn_lookup_tenant_by_stripe_subscription_id(text) TO {_GRANTEE}"
        ))
    else:
        print(
            f"[q2r3s4t5u6v7] AVISO: el rol '{_GRANTEE}' no existe todavía en este entorno — "
            f"la función se creó pero sin GRANT EXECUTE. Correr scripts/setup_db_user.py y "
            f"luego: GRANT EXECUTE ON FUNCTION fn_lookup_tenant_by_stripe_subscription_id(text) TO {_GRANTEE};"
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP FUNCTION IF EXISTS fn_lookup_tenant_by_stripe_subscription_id(text)"))
