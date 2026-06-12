"""Add Row-Level Security (RLS) for multi-tenant isolation.

Revision ID: h4i5j6k7l8m9
Revises: g3b4c5d6e7f8
Create Date: 2026-06-11

For every table with a direct tenant_id column: enables RLS + FORCE RLS and
creates SELECT/INSERT/UPDATE/DELETE policies gated on
current_setting('app.current_tenant_id', TRUE)::uuid.

Tables without a direct tenant_id (conversations, messages, lead_tags) use
subquery-based policies that resolve the owning tenant via their FK chain.

Skipped: tenants, companies (tree roots), alembic_version.

NOTES:
  · PostgreSQL superusers bypass RLS by default; FORCE only removes the owner
    bypass. Policies are enforced on the application user (walix_app).
  · The app must call set_config('app.current_tenant_id', <uuid>, FALSE)
    before any query. The FastAPI get_db dependency handles this.
  · current_setting(..., TRUE) (missing_ok=TRUE) returns NULL when the setting
    is absent, which makes no rows match — safe default.
  · Tables that do not yet exist are silently skipped.
"""

from alembic import op
from sqlalchemy import text


revision = "h4i5j6k7l8m9"
down_revision = "g3b4c5d6e7f8"
branch_labels = None
depends_on = None

# ── Helpers ───────────────────────────────────────────────────────────────────

_TENANT_EXPR = "current_setting('app.current_tenant_id', TRUE)::uuid"


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_schema = 'public' AND table_name = :t"
            ")"
        ),
        {"t": table},
    ).scalar()


def _enable_rls(conn, table: str) -> None:
    """Enable RLS and create the four standard tenant-isolation policies."""
    conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_select ON {table}"
        f"  FOR SELECT USING (tenant_id = {_TENANT_EXPR})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_insert ON {table}"
        f"  FOR INSERT WITH CHECK (tenant_id = {_TENANT_EXPR})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_update ON {table}"
        f"  FOR UPDATE USING (tenant_id = {_TENANT_EXPR})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_delete ON {table}"
        f"  FOR DELETE USING (tenant_id = {_TENANT_EXPR})"
    ))


def _disable_rls(conn, table: str) -> None:
    """Drop policies and disable RLS."""
    for op_type in ("select", "insert", "update", "delete"):
        conn.execute(text(
            f"DROP POLICY IF EXISTS tenant_isolation_{op_type} ON {table}"
        ))
    conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    conn.execute(text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))


# ── Tables: direct tenant_id ──────────────────────────────────────────────────

_DIRECT_TABLES = [
    "leads",
    "users",
    "branches",
    "knowledge_documents",
    "knowledge_chunks",
    "lead_activities",
    "agent_suggestions",
    "lead_scores",
    "daily_metrics",
    "sentiment_snapshots",
    "pipeline_stages",
    "onboarding_drafts",
    "meta_lead_configs",
    "activities",
    "tags",
    "ai_command_logs",
    "alert_rules",
    "support_sessions",
]

# ── Tables: no direct tenant_id — subquery policies ──────────────────────────

def _enable_rls_conversations(conn) -> None:
    conn.execute(text("ALTER TABLE conversations ENABLE ROW LEVEL SECURITY"))
    conn.execute(text("ALTER TABLE conversations FORCE ROW LEVEL SECURITY"))
    _subq = (
        f"branch_id IN ("
        f"  SELECT id FROM branches WHERE tenant_id = {_TENANT_EXPR}"
        f")"
    )
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_select ON conversations FOR SELECT USING ({_subq})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_insert ON conversations FOR INSERT WITH CHECK ({_subq})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_update ON conversations FOR UPDATE USING ({_subq})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_delete ON conversations FOR DELETE USING ({_subq})"
    ))


def _enable_rls_messages(conn) -> None:
    conn.execute(text("ALTER TABLE messages ENABLE ROW LEVEL SECURITY"))
    conn.execute(text("ALTER TABLE messages FORCE ROW LEVEL SECURITY"))
    _subq = (
        f"conversation_id IN ("
        f"  SELECT c.id FROM conversations c"
        f"  JOIN branches b ON b.id = c.branch_id"
        f"  WHERE b.tenant_id = {_TENANT_EXPR}"
        f")"
    )
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_select ON messages FOR SELECT USING ({_subq})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_insert ON messages FOR INSERT WITH CHECK ({_subq})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_update ON messages FOR UPDATE USING ({_subq})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_delete ON messages FOR DELETE USING ({_subq})"
    ))


def _enable_rls_lead_tags(conn) -> None:
    conn.execute(text("ALTER TABLE lead_tags ENABLE ROW LEVEL SECURITY"))
    conn.execute(text("ALTER TABLE lead_tags FORCE ROW LEVEL SECURITY"))
    _subq = (
        f"lead_id IN ("
        f"  SELECT id FROM leads WHERE tenant_id = {_TENANT_EXPR}"
        f")"
    )
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_select ON lead_tags FOR SELECT USING ({_subq})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_insert ON lead_tags FOR INSERT WITH CHECK ({_subq})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_update ON lead_tags FOR UPDATE USING ({_subq})"
    ))
    conn.execute(text(
        f"CREATE POLICY tenant_isolation_delete ON lead_tags FOR DELETE USING ({_subq})"
    ))


def _disable_rls_indirect(conn, table: str) -> None:
    for op_type in ("select", "insert", "update", "delete"):
        conn.execute(text(
            f"DROP POLICY IF EXISTS tenant_isolation_{op_type} ON {table}"
        ))
    conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    conn.execute(text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))


# ── Upgrade / Downgrade ───────────────────────────────────────────────────────

def upgrade() -> None:
    conn = op.get_bind()

    for table in _DIRECT_TABLES:
        if _table_exists(conn, table):
            _enable_rls(conn, table)

    for table, fn in [
        ("conversations", _enable_rls_conversations),
        ("messages", _enable_rls_messages),
        ("lead_tags", _enable_rls_lead_tags),
    ]:
        if _table_exists(conn, table):
            fn(conn)


def downgrade() -> None:
    conn = op.get_bind()

    for table in _DIRECT_TABLES:
        if _table_exists(conn, table):
            _disable_rls(conn, table)

    for table in ("conversations", "messages", "lead_tags"):
        if _table_exists(conn, table):
            _disable_rls_indirect(conn, table)
