"""Team and user management endpoints for Walix.

Routes:
  GET   /api/branches/{branch_id}/team
  POST  /api/branches/{branch_id}/team
  PUT   /api/users/{user_id}
  PATCH /api/users/{user_id}/toggle
  POST  /api/users/{user_id}/reset-password
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.roles import MULTI_BRANCH_ROLES
from app.core.security import hash_password, verify_password
from app.models.tenant import Branch
from app.models.user import User, UserRole

# Two routers share this module: branch-scoped team routes + user-level routes.
team_router = APIRouter(prefix="/branches", tags=["team"])
users_router = APIRouter(prefix="/users", tags=["users"])

_ROLE_ORDER: dict[UserRole, int] = {
    UserRole.OWNER: 0,
    UserRole.IT: 1,
    UserRole.GERENTE: 2,
    UserRole.DOCTOR: 3,
    UserRole.ASESOR: 4,
    UserRole.SOPORTE: 5,
}

_MIN_PASSWORD_LEN = 8


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    wa_phone: str | None
    is_active: bool
    branch_id: uuid.UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenantUserOut(BaseModel):
    """Lightweight DTO for directory lookups — no email/wa_phone exposed."""
    id: uuid.UUID
    name: str
    role: UserRole
    branch_id: uuid.UUID | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class CreateUserRequest(BaseModel):
    name: str
    email: str
    role: UserRole = UserRole.ASESOR
    wa_phone: str | None = None
    password: str


class UpdateUserRequest(BaseModel):
    name: str | None = None
    wa_phone: str | None = None
    role: UserRole | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str
    current_password: str | None = None


# ── Access helpers ─────────────────────────────────────────────────────────────

async def _get_branch_for_tenant(
    branch_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> Branch:
    branch = await db.get(Branch, branch_id)
    if branch is None or branch.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    return branch


async def _get_user_for_tenant(
    user_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> User:
    target = await db.get(User, user_id)
    if target is None or target.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return target


def _require_owner(user: User) -> None:
    if user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el owner puede realizar esta acción",
        )


def _check_team_read_access(user: User, branch_id: uuid.UUID) -> None:
    """Owner can read any branch; gerente only their own."""
    if user.role == UserRole.OWNER:
        return
    if user.role == UserRole.GERENTE:
        if user.branch_id != branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puedes ver el equipo de tu propia sucursal",
            )
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Solo el owner o gerente pueden consultar el equipo",
    )


# ── GET /branches/{branch_id}/team ────────────────────────────────────────────

@team_router.get("/{branch_id}/team", response_model=list[UserOut])
async def list_team(
    branch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    """Lists all users for a branch: active first, then inactive; within each group by role."""
    _check_team_read_access(current_user, branch_id)
    await _get_branch_for_tenant(branch_id, current_user.tenant_id, db)

    rows = await db.execute(select(User).where(User.branch_id == branch_id))
    users = rows.scalars().all()

    sorted_users = sorted(
        users,
        key=lambda u: (0 if u.is_active else 1, _ROLE_ORDER.get(u.role, 9), u.name),
    )
    return [UserOut.model_validate(u) for u in sorted_users]


# ── POST /branches/{branch_id}/team ───────────────────────────────────────────

@team_router.post("/{branch_id}/team", response_model=UserOut, status_code=201)
async def create_team_member(
    branch_id: uuid.UUID,
    body: CreateUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Creates a new user and assigns them to the branch. Owner only."""
    _require_owner(current_user)
    await _get_branch_for_tenant(branch_id, current_user.tenant_id, db)

    if len(body.password) < _MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La contraseña debe tener al menos {_MIN_PASSWORD_LEN} caracteres",
        )

    normalized_email = body.email.lower().strip()

    # Email is globally unique in the DB — check early with a clear message
    existing = await db.execute(
        select(User).where(User.email == normalized_email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario registrado con ese email",
        )

    user = User(
        tenant_id=current_user.tenant_id,
        branch_id=branch_id,
        email=normalized_email,
        name=body.name.strip(),
        hashed_password=hash_password(body.password),
        role=body.role,
        wa_phone=body.wa_phone,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


# ── GET /users — tenant directory (lightweight, all authenticated roles) ──────

@users_router.get("", response_model=list[TenantUserOut])
async def list_tenant_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TenantUserOut]:
    """Returns active users visible to the caller.

    MULTI_BRANCH_ROLES (owner/IT/platform_owner) → all active users of the tenant.
    Everyone else → only active users in the same branch.
    No email or wa_phone is exposed.
    """
    q = select(User).where(
        User.tenant_id == current_user.tenant_id,
        User.is_active.is_(True),
    )
    if current_user.role not in MULTI_BRANCH_ROLES:
        q = q.where(User.branch_id == current_user.branch_id)
    q = q.order_by(User.name)
    rows = (await db.execute(q)).scalars().all()
    return [TenantUserOut.model_validate(r) for r in rows]


# ── PUT /users/{user_id} ──────────────────────────────────────────────────────

@users_router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Updates name, wa_phone, or role.

    Owner: can edit any user in the tenant and change roles.
    Others: can only edit their own name and wa_phone (no role changes).
    Email is immutable.
    """
    target = await _get_user_for_tenant(user_id, current_user.tenant_id, db)

    is_self = target.id == current_user.id
    is_owner = current_user.role == UserRole.OWNER

    if not is_owner and not is_self:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes editar tu propio perfil",
        )

    if body.role is not None and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el owner puede cambiar roles",
        )

    if body.name is not None:
        target.name = body.name.strip()
    if body.wa_phone is not None:
        target.wa_phone = body.wa_phone or None
    if body.role is not None:
        target.role = body.role

    await db.commit()
    await db.refresh(target)
    return UserOut.model_validate(target)


# ── PATCH /users/{user_id}/toggle ─────────────────────────────────────────────

@users_router.patch("/{user_id}/toggle", response_model=UserOut)
async def toggle_active(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Flips is_active for a user. Owner only.

    Cannot deactivate self if they are the last active owner in the tenant.
    """
    _require_owner(current_user)
    target = await _get_user_for_tenant(user_id, current_user.tenant_id, db)

    # Guard: cannot lose the last active owner
    if target.id == current_user.id and target.is_active:
        count_row = await db.execute(
            select(func.count(User.id)).where(
                User.tenant_id == current_user.tenant_id,
                User.role == UserRole.OWNER,
                User.is_active.is_(True),
            )
        )
        if (count_row.scalar() or 0) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No puedes desactivarte si eres el único owner activo del tenant",
            )

    target.is_active = not target.is_active
    await db.commit()
    await db.refresh(target)
    return UserOut.model_validate(target)


# ── POST /users/{user_id}/reset-password ──────────────────────────────────────

@users_router.post("/{user_id}/reset-password", status_code=204)
async def reset_password(
    user_id: uuid.UUID,
    body: ResetPasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Resets a user's password.

    Owner can reset any user's password without current_password.
    Self-reset (any role) always requires current_password for verification.
    """
    target = await _get_user_for_tenant(user_id, current_user.tenant_id, db)

    is_self = target.id == current_user.id
    is_owner = current_user.role == UserRole.OWNER

    if not is_owner and not is_self:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin permisos para cambiar la contraseña de este usuario",
        )

    if is_self:
        # Changing own password — always verify current identity
        if not body.current_password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Debes enviar current_password para cambiar tu propia contraseña",
            )
        if not verify_password(body.current_password, target.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Contraseña actual incorrecta",
            )
    # else: owner resetting another user — no current_password required

    if len(body.new_password) < _MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La nueva contraseña debe tener al menos {_MIN_PASSWORD_LEN} caracteres",
        )

    target.hashed_password = hash_password(body.new_password)
    await db.commit()
