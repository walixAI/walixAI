"""multi-pipeline: tabla pipelines + pipeline_id en pipeline_stages

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2026-07-29

Introduce la tabla pipelines y vincula cada pipeline_stage a un pipeline.
El backfill crea un pipeline default por cada branch que ya tenga stages,
luego asigna pipeline_id en pipeline_stages vía UPDATE correlacionado.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "y2z3a4b5c6d7"
down_revision = "x1y2z3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Crear tabla pipelines
    op.create_table(
        "pipelines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "position", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("branch_id", "name", name="uq_pipelines_branch_name"),
    )
    op.create_index("ix_pipelines_tenant_id", "pipelines", ["tenant_id"])
    op.create_index("ix_pipelines_branch_id", "pipelines", ["branch_id"])

    # 2. Backfill: un pipeline default por cada branch que ya tenga stages
    op.execute(
        """
        INSERT INTO pipelines (id, tenant_id, branch_id, name, is_default, position)
        SELECT
            gen_random_uuid(),
            tenant_id,
            branch_id,
            'Pipeline Principal',
            true,
            0
        FROM (
            SELECT DISTINCT tenant_id, branch_id FROM pipeline_stages
        ) AS branches_with_stages
        """
    )

    # 3. Agregar pipeline_id nullable temporalmente para el UPDATE
    op.add_column(
        "pipeline_stages",
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 4. Asignar pipeline_id desde el pipeline default de cada branch
    op.execute(
        """
        UPDATE pipeline_stages ps
        SET pipeline_id = p.id
        FROM pipelines p
        WHERE p.branch_id = ps.branch_id
          AND p.is_default = true
        """
    )

    # 5. Verificar que no quedaron NULL (safeguard — solo en modo online, no en dry-run)
    if not op.get_context().as_sql:
        conn = op.get_bind()
        null_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM pipeline_stages WHERE pipeline_id IS NULL")
        ).scalar()
        if null_count and null_count > 0:
            raise RuntimeError(
                f"Backfill incompleto: {null_count} pipeline_stages sin pipeline_id. "
                "Revisa que el INSERT del paso 2 cubrió todas las branches con stages."
            )

    # 6. Hacer pipeline_id NOT NULL
    op.alter_column("pipeline_stages", "pipeline_id", nullable=False)

    # 7. Índice en pipeline_stages.pipeline_id
    op.create_index(
        "ix_pipeline_stages_pipeline_id", "pipeline_stages", ["pipeline_id"]
    )

    # 8. FK de pipeline_stages → pipelines
    op.create_foreign_key(
        "fk_pipeline_stages_pipeline_id",
        "pipeline_stages",
        "pipelines",
        ["pipeline_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_pipeline_stages_pipeline_id", "pipeline_stages", type_="foreignkey"
    )
    op.drop_index("ix_pipeline_stages_pipeline_id", table_name="pipeline_stages")
    op.drop_column("pipeline_stages", "pipeline_id")
    op.drop_index("ix_pipelines_branch_id", table_name="pipelines")
    op.drop_index("ix_pipelines_tenant_id", table_name="pipelines")
    op.drop_table("pipelines")
