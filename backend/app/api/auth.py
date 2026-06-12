import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    hash_password,  # re-exported for callers that need to seed users
    verify_password,
    verify_token,
)
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer_scheme = HTTPBearer(auto_error=True)


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginUserOut(BaseModel):
    id: uuid.UUID
    name: str
    role: UserRole
    branch_id: uuid.UUID | None
    tenant_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    access_token: str
    user: LoginUserOut


class UserMeOut(LoginUserOut):
    email: str
    is_active: bool


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_token(creds.credentials)
    except JWTError:
        raise credentials_error

    sub = payload.get("sub")
    if not sub:
        raise credentials_error
    try:
        user_id = uuid.UUID(sub)
    except (ValueError, TypeError):
        raise credentials_error

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Este campo no puede estar vacío")
        return v.strip()


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este correo ya está registrado",
        )

    # Workspace placeholder — se configura en el wizard de onboarding
    workspace_name = body.email.split("@")[0].replace(".", " ").title()

    tenant = Tenant(
        name=workspace_name,
        email=body.email,
        plan=TenantPlan.STARTER,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    company = Company(
        tenant_id=tenant.id,
        name=workspace_name,
    )
    db.add(company)
    await db.flush()

    branch = Branch(
        company_id=company.id,
        tenant_id=tenant.id,
        name="Sede Principal",
        is_active=True,
    )
    db.add(branch)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        branch_id=branch.id,
        email=body.email,
        name=body.name,
        hashed_password=hash_password(body.password),
        role=UserRole.OWNER,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "tenant_id": str(user.tenant_id)})
    return LoginResponse(access_token=token, user=LoginUserOut.model_validate(user))


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Same response for unknown email and wrong password — avoids leaking which
    # emails exist via timing or message differences.
    if user is None or not user.is_active or not verify_password(
        body.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token({"sub": str(user.id), "tenant_id": str(user.tenant_id)})
    return LoginResponse(access_token=token, user=LoginUserOut.model_validate(user))


@router.get("/me", response_model=UserMeOut)
async def me(current_user: User = Depends(get_current_user)) -> UserMeOut:
    return UserMeOut.model_validate(current_user)


__all__ = ["router", "get_current_user", "hash_password"]
