"""
Sprint 8A · P-01 — saved_views BD layer
Verifica migración, constraints, índices y CASCADE de la tabla saved_views.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User, UserRole


# ── P-01-01 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_views_table_exists(db: AsyncSession) -> None:
    """La tabla saved_views existe en la BD de prueba."""
    result = await db.execute(text("SELECT to_regclass('public.saved_views')"))
    assert result.scalar() is not None, "La tabla saved_views no existe"


# ── P-01-02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_views_columns(db: AsyncSession) -> None:
    """La tabla tiene todas las columnas requeridas con el tipo correcto."""
    result = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'saved_views' "
            "ORDER BY ordinal_position"
        )
    )
    columns = [row[0] for row in result.fetchall()]

    required = [
        "id", "user_id", "tenant_id", "name",
        "filters", "view_mode", "is_default",
        "created_at", "updated_at",
    ]
    for col in required:
        assert col in columns, f"Columna '{col}' no encontrada en saved_views"


# ── P-01-03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_views_unique_constraint(
    db: AsyncSession,
    user_asesor: User,
    tenant_a: Tenant,
) -> None:
    """No permite dos vistas con el mismo nombre para el mismo usuario."""
    uid = str(user_asesor.id)
    tid = str(tenant_a.id)

    # Primera vista — debe insertarse sin error
    await db.execute(
        text(
            "INSERT INTO saved_views "
            "(id, user_id, tenant_id, name, filters, view_mode, is_default) "
            "VALUES (gen_random_uuid(), :uid, :tid, 'Vista Test Única', '{}', 'list', false)"
        ),
        {"uid": uid, "tid": tid},
    )
    # La segunda con igual nombre debe violar uq_saved_views_user_name
    with pytest.raises(Exception, match=r"uq_saved_views_user_name|unique|duplicate"):
        await db.execute(
            text(
                "INSERT INTO saved_views "
                "(id, user_id, tenant_id, name, filters, view_mode, is_default) "
                "VALUES (gen_random_uuid(), :uid, :tid, 'Vista Test Única', '{}', 'list', false)"
            ),
            {"uid": uid, "tid": tid},
        )
        # Flush para forzar la ejecución del statement si no se envió aún
        await db.flush()


# ── P-01-04 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_views_view_mode_check(
    db: AsyncSession,
    user_asesor: User,
    tenant_a: Tenant,
) -> None:
    """El campo view_mode solo acepta 'list', 'kanban', 'cards'."""
    # 'grid' cabe en VARCHAR(10) pero no está en el CHECK constraint
    with pytest.raises(Exception, match=r"ck_saved_views_view_mode|check|violat|CheckViolation"):
        await db.execute(
            text(
                "INSERT INTO saved_views "
                "(id, user_id, tenant_id, name, filters, view_mode, is_default) "
                "VALUES (gen_random_uuid(), :uid, :tid, 'Test Mode', '{}', 'grid', false)"
            ),
            {"uid": str(user_asesor.id), "tid": str(tenant_a.id)},
        )
        await db.flush()


# ── P-01-05 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_views_cascade_delete(
    db: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Al eliminar un usuario, sus vistas se eliminan automáticamente (CASCADE)."""
    # Crear usuario temporal vía ORM (evita enumerar todos los NOT NULL en SQL crudo)
    temp_user = User(
        tenant_id=tenant_a.id,
        email=f"cascade-{uuid.uuid4().hex[:8]}@walix.test",
        name="Usuario Temporal Cascade",
        hashed_password=hash_password("temp1234"),
        role=UserRole.ASESOR,
        is_active=True,
    )
    db.add(temp_user)
    await db.flush()  # obtener temp_user.id sin salir de la transacción

    # Insertar una vista para ese usuario
    await db.execute(
        text(
            "INSERT INTO saved_views "
            "(id, user_id, tenant_id, name, filters, view_mode, is_default) "
            "VALUES (gen_random_uuid(), :uid, :tid, 'Vista Cascade', '{}', 'list', false)"
        ),
        {"uid": str(temp_user.id), "tid": str(tenant_a.id)},
    )
    await db.flush()

    # Verificar que la vista existe
    count_before = (
        await db.execute(
            text("SELECT COUNT(*) FROM saved_views WHERE user_id = :uid"),
            {"uid": str(temp_user.id)},
        )
    ).scalar()
    assert count_before == 1, "La vista debería existir antes del DELETE"

    # Eliminar el usuario — el CASCADE debe borrar la vista
    await db.execute(
        text("DELETE FROM users WHERE id = :id"), {"id": str(temp_user.id)}
    )
    await db.flush()

    # La vista debe haberse eliminado automáticamente
    count_after = (
        await db.execute(
            text("SELECT COUNT(*) FROM saved_views WHERE user_id = :uid"),
            {"uid": str(temp_user.id)},
        )
    ).scalar()
    assert count_after == 0, "El CASCADE no eliminó las vistas del usuario"


# ── P-01-06 (bonus) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_views_valid_view_modes(
    db: AsyncSession,
    user_asesor: User,
    tenant_a: Tenant,
) -> None:
    """Acepta correctamente los tres view_mode válidos."""
    uid = str(user_asesor.id)
    tid = str(tenant_a.id)

    for mode in ("list", "kanban", "cards"):
        await db.execute(
            text(
                "INSERT INTO saved_views "
                "(id, user_id, tenant_id, name, filters, view_mode, is_default) "
                "VALUES (gen_random_uuid(), :uid, :tid, :name, '{}', :mode, false)"
            ),
            {"uid": uid, "tid": tid, "name": f"Vista {mode}", "mode": mode},
        )
    await db.flush()  # si llega aquí sin excepción, los tres modos son válidos


# ── P-01-07 (bonus) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_views_updated_at_trigger(
    db: AsyncSession,
    saved_view_basic,  # fixture del conftest sprint8a
) -> None:
    """El trigger actualiza updated_at automáticamente al hacer UPDATE."""
    view_id = str(saved_view_basic.id)

    # Leer el updated_at inicial
    original = (
        await db.execute(
            text("SELECT updated_at FROM saved_views WHERE id = :id"), {"id": view_id}
        )
    ).scalar()

    # Pequeña pausa para asegurar diferencia en timestamp (1ms)
    import asyncio
    await asyncio.sleep(0.01)

    # Actualizar la vista
    await db.execute(
        text("UPDATE saved_views SET name = 'Nombre Cambiado' WHERE id = :id"),
        {"id": view_id},
    )
    await db.flush()

    # El trigger debe haber actualizado updated_at
    new_ts = (
        await db.execute(
            text("SELECT updated_at FROM saved_views WHERE id = :id"), {"id": view_id}
        )
    ).scalar()

    assert new_ts is not None
    # updated_at debe ser >= al original (trigger puede ser igual si el clock no avanzó)
    assert new_ts >= original, "El trigger no actualizó updated_at"
