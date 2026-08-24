import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, set_tenant_context
from app.core.security import (
    create_access_token,
    hash_password,  # re-exported for callers that need to seed users
    verify_password,
    verify_token,
)
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])
v2_router = APIRouter(prefix="/v2/auth", tags=["auth"])

_bearer_scheme = HTTPBearer(auto_error=True)


async def _resolve_tenant_by_email(db: AsyncSession, email: str) -> uuid.UUID | None:
    """Pre-tenant lookup: which tenant (if any) owns a user with this email.

    Uses fn_lookup_tenant_by_email (SECURITY DEFINER, migration
    l7m8n9o0p1q2) instead of `SELECT * FROM users WHERE email = ...`
    directly, because at this point in the flow there is no tenant context
    set yet — under RLS with a non-bypass runtime role (walix_app), a plain
    SELECT would never see any row, no matter which tenant the email
    belongs to. The function returns ONLY tenant_id, never the row itself.
    """
    result = await db.execute(text("SELECT fn_lookup_tenant_by_email(:email)"), {"email": email})
    return result.scalar_one_or_none()


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


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    industry_key: str = "generico"
    industry_label: str | None = None
    entity_name: str = "Contacto"
    entity_plural: str = "Contactos"
    deal_name: str = "Oportunidad"
    deal_plural: str = "Oportunidades"
    contact_statuses: list = []
    deal_type_options: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class MeResponse(BaseModel):
    user: UserMeOut
    tenant: TenantOut


async def get_current_user(
    request: Request,
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

    # Platform-owner impersonation (hallazgo #9, docs/PERMISSIONS_DRIFT_BACKLOG.md):
    # an impersonation token (see platform.py::impersonate_tenant) carries a
    # tenant_id claim for the TARGET tenant, distinct from this row's own
    # tenant_id (the platform_owner's home tenant). TenantContextMiddleware
    # already uses that claim correctly to activate RLS, but the 213+ call
    # sites across app/api/ that filter by current_user.tenant_id at the
    # application layer (outside RLS) were still using the platform_owner's
    # own tenant_id. Overriding it here — in memory only, never flushed or
    # committed from this function, never via session.merge() — makes those
    # filters see the impersonated tenant like TenantContextMiddleware/RLS
    # already do.
    request.state.is_impersonating = False
    token_tenant_id = payload.get("tenant_id")
    if token_tenant_id:
        try:
            claim_tenant_id = uuid.UUID(token_tenant_id)
        except (ValueError, TypeError):
            claim_tenant_id = None
        if claim_tenant_id is not None and claim_tenant_id != user.tenant_id:
            user.tenant_id = claim_tenant_id
            request.state.is_impersonating = True
            # hallazgo #10 (docs/PERMISSIONS_DRIFT_BACKLOG.md, encontrado al
            # implementar el #9): la asignación de arriba marca `user` dirty
            # en la sesión de SQLAlchemy automáticamente, sin necesidad de
            # session.merge() ni db.add(). Si un db.commit() posterior en
            # esta misma request (aunque no tenga nada que ver con
            # current_user — ej. agents.py::list_suggestions, un GET que
            # comitea al marcar sugerencias vencidas) hiciera flush de la
            # sesión, persistiría el tenant_id impersonado sobre la fila
            # REAL del platform_owner. expunge() lo desprende de la sesión
            # para que ningún commit posterior pueda arrastrar el cambio.
            db.expunge(user)

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
    if await _resolve_tenant_by_email(db, body.email) is not None:
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
    # El tenant recién se creó en esta misma transacción — a partir de acá
    # SÍ lo conocemos, así que las siguientes filas (RLS-protegidas) pueden
    # insertarse normalmente contra ese contexto.
    await set_tenant_context(db, tenant.id)

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
    user = None
    tenant_id = await _resolve_tenant_by_email(db, body.email)
    if tenant_id is not None:
        await set_tenant_context(db, tenant_id)
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


@router.get("/me", response_model=MeResponse)
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    tenant = await db.get(Tenant, current_user.tenant_id)
    tenant_out = TenantOut(
        id=tenant.id if tenant else current_user.tenant_id,
        name=tenant.name if tenant else "",
        industry_key=tenant.industry_key if tenant else "generico",
        industry_label=tenant.industry_label if tenant else None,
        entity_name=(tenant.entity_name or "Contacto") if tenant else "Contacto",
        entity_plural=(tenant.entity_plural or "Contactos") if tenant else "Contactos",
        deal_name=(tenant.deal_name or "Oportunidad") if tenant else "Oportunidad",
        deal_plural=(tenant.deal_plural or "Oportunidades") if tenant else "Oportunidades",
        contact_statuses=tenant.contact_statuses_config or [] if tenant else [],
        deal_type_options=tenant.deal_type_options or [] if tenant else [],
    )
    return MeResponse(
        user=UserMeOut.model_validate(current_user),
        tenant=tenant_out,
    )


# ── POST /auth/check-email ────────────────────────────────────────────────────

class CheckEmailRequest(BaseModel):
    email: str


class CheckEmailResponse(BaseModel):
    available: bool


@router.post("/check-email", response_model=CheckEmailResponse)
async def check_email(
    body: CheckEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> CheckEmailResponse:
    """Return {available: true} if the email is not yet registered."""
    tenant_id = await _resolve_tenant_by_email(db, body.email.strip().lower())
    return CheckEmailResponse(available=tenant_id is None)


# ── POST /v2/auth/register ────────────────────────────────────────────────────

_TRIAL_DAYS = 14

REFERRAL_SOURCES = ["google", "instagram", "facebook", "recomendacion", "otro"]


class RegisterV2Request(BaseModel):
    name: str
    email: str
    password: str
    workspace_name: str
    phone: str | None = None
    referral_source: str | None = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Este campo no puede estar vacío")
        return v.strip()

    @field_validator("workspace_name")
    @classmethod
    def workspace_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El nombre del negocio no puede estar vacío")
        return v.strip()


@v2_router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register_v2(
    body: RegisterV2Request,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Full tenant registration: creates Tenant + Company + Branch + User in one transaction.

    Sets plan=TRIAL with trial_ends_at = now + 14 days.
    Owner gets branch_id=None (access to all branches).
    """
    email = body.email.strip().lower()

    if await _resolve_tenant_by_email(db, email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este correo ya está registrado",
        )

    now = datetime.now(timezone.utc)
    trial_ends_at = now + timedelta(days=_TRIAL_DAYS)

    tenant = Tenant(
        name=body.workspace_name,
        email=email,
        plan=TenantPlan.TRIAL,
        is_active=True,
        trial_ends_at=trial_ends_at,
        industry_key="generico",
        referral_source=body.referral_source,
    )
    db.add(tenant)
    await db.flush()
    # Idem register(): recién acá conocemos el tenant nuevo.
    await set_tenant_context(db, tenant.id)

    company = Company(
        tenant_id=tenant.id,
        name=body.workspace_name,
    )
    db.add(company)
    await db.flush()

    branch = Branch(
        company_id=company.id,
        tenant_id=tenant.id,
        name=f"{body.workspace_name} · Principal",
        is_active=True,
    )
    db.add(branch)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        branch_id=None,  # owners access all branches
        email=email,
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


__all__ = ["router", "v2_router", "get_current_user", "hash_password"]
