import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.lead import Lead, LeadStatus
from app.models.tenant import Branch
from app.models.user import User, UserRole

router = APIRouter(prefix="/branches", tags=["branches"])

_ACTIVE_STATUSES = (LeadStatus.CALIFICADO, LeadStatus.EN_CALIFICACION)
_AGENT_ROLES = (UserRole.DOCTOR, UserRole.ASESOR, UserRole.GERENTE)


class AgentOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    active_leads: int
    wa_phone: str | None


async def _require_branch_access(
    user: User, branch_id: uuid.UUID, db: AsyncSession
) -> None:
    """Raises 403 if the user has no access to the given branch."""
    if user.branch_id == branch_id:
        return
    if user.role in (UserRole.OWNER, UserRole.GERENTE):
        branch = await db.get(Branch, branch_id)
        if branch and branch.tenant_id == user.tenant_id:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes acceso a esta sucursal",
    )


@router.get("/{branch_id}/agents", response_model=list[AgentOut])
async def list_branch_agents(
    branch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentOut]:
    """Returns active agents in the branch ordered by workload (fewest active leads first).

    Active leads = leads with status calificado or en_calificacion assigned to the user.
    Doctors appear before asesores, who appear before gerentes.
    """
    await _require_branch_access(current_user, branch_id, db)

    # Correlated subquery: count active leads assigned to each user
    active_leads_sq = (
        select(func.count(Lead.id))
        .where(
            Lead.assigned_to == User.id,
            Lead.status.in_(_ACTIVE_STATUSES),
        )
        .correlate(User)
        .scalar_subquery()
    )

    rows = await db.execute(
        select(User, active_leads_sq.label("active_leads"))
        .where(
            User.branch_id == branch_id,
            User.is_active.is_(True),
            User.role.in_(_AGENT_ROLES),
        )
    )

    role_order = {UserRole.DOCTOR: 0, UserRole.ASESOR: 1, UserRole.GERENTE: 2}
    agents: list[AgentOut] = []
    for user, active_leads in rows.all():
        agents.append(
            AgentOut(
                id=user.id,
                name=user.name,
                role=user.role,
                active_leads=active_leads,
                wa_phone=user.wa_phone,
            )
        )

    agents.sort(key=lambda a: (role_order.get(UserRole(a.role), 9), a.active_leads))
    return agents
