"""Role-based dashboard endpoint for Walix.

GET /api/dashboard returns a tailored response based on the caller's role:
  asesor         → my leads, recent activity, pending suggestions, mini pipeline
  gerente        → pipeline overview, team performance, sentiment, at-risk leads
  owner          → multi-branch consolidated, MRR, conversion comparison
  it             → integrations, AI usage, config alerts
  platform_owner → redirect to /api/platform/stats
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.redis import redis_client
from app.models.activity import ActivityType, LeadActivity
from app.models.agent import AgentSuggestion
from app.models.ai_log import AICommandLog
from app.models.conversation import Conversation, Message
from app.models.lead import Lead, LeadStatus
from app.models.metrics import SentimentSnapshot
from app.models.pipeline import PipelineStage
from app.models.scoring import LeadScore
from app.models.tenant import Branch, Tenant
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_TERMINAL = [LeadStatus.PERDIDO, LeadStatus.CALIFICADO]
CACHE_TTL = 300  # 5 min — aligns with daily_metrics update cadence

# MRR per plan (USD) — mirrors platform.py
_PLAN_MRR: dict[str, int] = {
    "starter": 29,
    "growth": 79,
    "business": 199,
    "enterprise": 499,
}


@router.get("")
async def get_dashboard(
    branch_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Role-adaptive dashboard. Returns a JSON structure tailored to the caller's role."""
    role = current_user.role

    if role == UserRole.PLATFORM_OWNER:
        return RedirectResponse(url="/api/platform/stats", status_code=307)

    # Cache key is per-user so each asesor sees their own leads.
    # Date suffix ensures the cache flushes at midnight (natural data boundary).
    today = datetime.now(timezone.utc).date().isoformat()
    cache_key = f"dashboard:{role}:{current_user.id}:{today}"

    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.warning("dashboard: Redis cache read failed key=%s", cache_key)

    if role == UserRole.IT:
        result: dict[str, Any] = await _it_dashboard(current_user, db)
    elif role == UserRole.OWNER:
        result = await _owner_dashboard(current_user, db)
    elif role == UserRole.GERENTE:
        resolved = _resolve_branch(branch_id, current_user)
        result = await _gerente_dashboard(resolved, current_user, db)
    else:
        # asesor / doctor / default
        resolved = _resolve_branch(branch_id, current_user)
        result = await _asesor_dashboard(resolved, current_user, db)

    try:
        await redis_client.set(cache_key, json.dumps(result, default=str), ex=CACHE_TTL)
    except Exception:
        logger.warning("dashboard: Redis cache write failed key=%s", cache_key)

    return result


# ── Asesor dashboard ──────────────────────────────────────────────────────────

async def _asesor_dashboard(
    branch_id: uuid.UUID, user: User, db: AsyncSession
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)

    # My leads (assigned to me)
    my_leads_result = await db.execute(
        select(Lead).where(
            Lead.branch_id == branch_id,
            Lead.assigned_to == user.id,
            Lead.status.notin_(_TERMINAL),
        ).order_by(Lead.updated_at.desc()).limit(20)
    )
    my_leads = my_leads_result.scalars().all()

    # Stage names
    stage_ids = {l.pipeline_stage_id for l in my_leads if l.pipeline_stage_id}
    stage_names: dict[uuid.UUID, str] = {}
    if stage_ids:
        sr = await db.execute(
            select(PipelineStage.id, PipelineStage.name).where(PipelineStage.id.in_(stage_ids))
        )
        stage_names = dict(sr.fetchall())

    # Recent activity (last 7 days)
    week_ago = now - timedelta(days=7)
    activity_result = await db.execute(
        select(LeadActivity)
        .join(Lead, LeadActivity.lead_id == Lead.id)
        .where(
            Lead.branch_id == branch_id,
            Lead.assigned_to == user.id,
            LeadActivity.created_at >= week_ago,
        )
        .order_by(LeadActivity.created_at.desc())
        .limit(20)
    )
    activities = activity_result.scalars().all()

    # Pending suggestions for this user
    suggestions_result = await db.execute(
        select(AgentSuggestion).where(
            AgentSuggestion.tenant_id == user.tenant_id,
            AgentSuggestion.target_user_id == user.id,
            AgentSuggestion.status == "suggested",
            AgentSuggestion.expires_at > now,
        ).order_by(AgentSuggestion.created_at.desc()).limit(5)
    )

    # Mini pipeline: leads count per stage
    mini_pipeline_result = await db.execute(
        select(Lead.pipeline_stage_id, func.count(Lead.id))
        .where(
            Lead.branch_id == branch_id,
            Lead.assigned_to == user.id,
            Lead.status.notin_(_TERMINAL),
        )
        .group_by(Lead.pipeline_stage_id)
    )

    return {
        "role": "asesor",
        "my_leads": [
            {
                "id": str(l.id),
                "name": l.name,
                "wa_phone": l.wa_phone,
                "status": getattr(l.status, "value", str(l.status)),
                "sentiment": getattr(l.sentiment, "value", str(l.sentiment)),
                "current_score": l.current_score,
                "current_score_trend": l.current_score_trend,
                "stage_name": stage_names.get(l.pipeline_stage_id),
                "updated_at": l.updated_at.isoformat(),
            }
            for l in my_leads
        ],
        "recent_activity": [
            {
                "activity_type": getattr(a.activity_type, "value", str(a.activity_type)),
                "lead_id": str(a.lead_id),
                "payload": a.payload,
                "created_at": a.created_at.isoformat(),
            }
            for a in activities
        ],
        "pending_suggestions": [
            {
                "id": str(s.id),
                "agent_type": s.agent_type,
                "suggestion_text": s.suggestion_text,
                "created_at": s.created_at.isoformat(),
            }
            for s in suggestions_result.scalars().all()
        ],
        "mini_pipeline": [
            {
                "stage_id": str(stage_id) if stage_id else None,
                "stage_name": stage_names.get(stage_id),
                "count": count,
            }
            for stage_id, count in mini_pipeline_result.fetchall()
        ],
    }


# ── Gerente dashboard ─────────────────────────────────────────────────────────

async def _gerente_dashboard(
    branch_id: uuid.UUID, user: User, db: AsyncSession
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)

    # Active leads by stage
    by_stage_result = await db.execute(
        select(Lead.pipeline_stage_id, func.count(Lead.id), func.avg(Lead.current_score))
        .where(
            Lead.branch_id == branch_id,
            Lead.status.notin_(_TERMINAL),
        )
        .group_by(Lead.pipeline_stage_id)
    )
    stage_ids: set[uuid.UUID] = set()
    by_stage_raw = by_stage_result.fetchall()
    for row in by_stage_raw:
        if row[0]:
            stage_ids.add(row[0])

    stage_names: dict[uuid.UUID, str] = {}
    if stage_ids:
        sr = await db.execute(
            select(PipelineStage.id, PipelineStage.name, PipelineStage.order_index)
            .where(PipelineStage.id.in_(stage_ids))
            .order_by(PipelineStage.order_index)
        )
        stage_names = {r[0]: r[1] for r in sr.fetchall()}

    # Team performance: asesores in branch
    asesores_result = await db.execute(
        select(User).where(
            User.branch_id == branch_id,
            User.role == UserRole.ASESOR.value,
            User.is_active.is_(True),
        )
    )
    asesores = asesores_result.scalars().all()
    team_perf = []
    for a in asesores:
        total_r = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.assigned_to == a.id, Lead.branch_id == branch_id
            )
        )
        total = total_r.scalar_one() or 0
        won_r = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.assigned_to == a.id,
                Lead.branch_id == branch_id,
                Lead.status == LeadStatus.CALIFICADO,
            )
        )
        won = won_r.scalar_one() or 0
        team_perf.append({
            "asesor_id": str(a.id),
            "name": a.name,
            "leads_assigned": total,
            "leads_won": won,
            "conversion_rate": round(won / total * 100, 1) if total else 0.0,
        })

    # Latest sentiment snapshot
    snap_r = await db.execute(
        select(SentimentSnapshot).where(
            SentimentSnapshot.branch_id == branch_id,
        ).order_by(SentimentSnapshot.snapshot_date.desc()).limit(1)
    )
    snap = snap_r.scalar_one_or_none()

    # At-risk leads (score < 30 in stage order_index >= 2)
    at_risk_result = await db.execute(
        select(Lead).where(
            Lead.branch_id == branch_id,
            Lead.status.notin_(_TERMINAL),
            Lead.current_score < 30,
            Lead.current_score.isnot(None),
        ).order_by(Lead.current_score.asc()).limit(10)
    )
    at_risk = at_risk_result.scalars().all()

    # Active automations count
    auto_count_r = await db.execute(
        select(func.count(AgentSuggestion.id)).where(
            AgentSuggestion.tenant_id == user.tenant_id,
            AgentSuggestion.status == "suggested",
            AgentSuggestion.expires_at > now,
        )
    )
    active_automations = auto_count_r.scalar_one() or 0

    total_active = sum(row[1] for row in by_stage_raw)

    return {
        "role": "gerente",
        "pipeline": {
            "total_active": total_active,
            "by_stage": [
                {
                    "stage_id": str(row[0]) if row[0] else None,
                    "stage_name": stage_names.get(row[0]),
                    "count": row[1],
                    "avg_score": round(float(row[2]), 1) if row[2] else None,
                }
                for row in by_stage_raw
            ],
        },
        "team_performance": team_perf,
        "sentiment_summary": {
            "overall_score": snap.overall_score if snap else None,
            "distribution": snap.distribution if snap else {},
            "snapshot_date": snap.snapshot_date.isoformat() if snap else None,
        },
        "at_risk_leads": [
            {
                "lead_id": str(l.id),
                "name": l.name,
                "score": l.current_score,
                "stage_name": stage_names.get(l.pipeline_stage_id),
            }
            for l in at_risk
        ],
        "active_automations": active_automations,
    }


# ── Owner dashboard ───────────────────────────────────────────────────────────

async def _owner_dashboard(user: User, db: AsyncSession) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_month_start = (month_start - timedelta(days=1)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    # Branches for this tenant
    branches_result = await db.execute(
        select(Branch).where(
            Branch.tenant_id == user.tenant_id,
            Branch.is_active.is_(True),
        )
    )
    branches = branches_result.scalars().all()

    branches_data = []
    for branch in branches:
        # Total active leads
        total_r = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.branch_id == branch.id,
                Lead.status.notin_(_TERMINAL),
            )
        )
        total_leads = total_r.scalar_one() or 0

        # Conversion this month
        won_r = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.branch_id == branch.id,
                Lead.status == LeadStatus.CALIFICADO,
                Lead.updated_at >= month_start,
            )
        )
        won = won_r.scalar_one() or 0

        created_r = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.branch_id == branch.id,
                Lead.created_at >= month_start,
            )
        )
        created = created_r.scalar_one() or 0

        # Latest sentiment
        snap_r = await db.execute(
            select(SentimentSnapshot.overall_score).where(
                SentimentSnapshot.branch_id == branch.id,
            ).order_by(SentimentSnapshot.snapshot_date.desc()).limit(1)
        )
        sentiment = snap_r.scalar_one_or_none()

        branches_data.append({
            "branch_id": str(branch.id),
            "branch_name": branch.name,
            "leads_active": total_leads,
            "leads_created_month": created,
            "leads_won_month": won,
            "conversion_rate": round(won / created * 100, 1) if created else 0.0,
            "sentiment_score": round(sentiment, 3) if sentiment else None,
        })

    # Tenant plan → MRR estimate
    tenant = await db.get(Tenant, user.tenant_id)
    plan_value = getattr(getattr(tenant, "plan", None), "value", "starter") if tenant else "starter"
    mrr_estimate = _PLAN_MRR.get(plan_value, 0)

    # Cross-branch conversion comparison (this month vs last)
    total_created_this = sum(b["leads_created_month"] for b in branches_data)
    total_won_this = sum(b["leads_won_month"] for b in branches_data)

    prev_created_r = await db.execute(
        select(func.count(Lead.id)).where(
            Lead.tenant_id == user.tenant_id,
            Lead.created_at >= prev_month_start,
            Lead.created_at < month_start,
        )
    )
    prev_created = prev_created_r.scalar_one() or 0
    prev_won_r = await db.execute(
        select(func.count(Lead.id)).where(
            Lead.tenant_id == user.tenant_id,
            Lead.status == LeadStatus.CALIFICADO,
            Lead.updated_at >= prev_month_start,
            Lead.updated_at < month_start,
        )
    )
    prev_won = prev_won_r.scalar_one() or 0

    # Cross-branch suggestions (pipeline/config agents)
    cross_sugg_r = await db.execute(
        select(AgentSuggestion).where(
            AgentSuggestion.tenant_id == user.tenant_id,
            AgentSuggestion.status == "suggested",
            AgentSuggestion.agent_type.in_(["pipeline", "config"]),
            AgentSuggestion.expires_at > now,
        ).order_by(AgentSuggestion.created_at.desc()).limit(5)
    )

    return {
        "role": "owner",
        "branches": branches_data,
        "mrr_estimate": mrr_estimate,
        "conversion_comparison": {
            "this_month": {
                "created": total_created_this,
                "won": total_won_this,
                "rate": round(total_won_this / total_created_this * 100, 1) if total_created_this else 0.0,
            },
            "last_month": {
                "created": prev_created,
                "won": prev_won,
                "rate": round(prev_won / prev_created * 100, 1) if prev_created else 0.0,
            },
        },
        "cross_branch_suggestions": [
            {
                "id": str(s.id),
                "agent_type": s.agent_type,
                "suggestion_text": s.suggestion_text,
                "created_at": s.created_at.isoformat(),
            }
            for s in cross_sugg_r.scalars().all()
        ],
    }


# ── IT dashboard ──────────────────────────────────────────────────────────────

async def _it_dashboard(user: User, db: AsyncSession) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Branch integration status
    branches_result = await db.execute(
        select(Branch).where(Branch.tenant_id == user.tenant_id)
    )
    branches = branches_result.scalars().all()
    with_wa = sum(1 for b in branches if b.wa_phone_number_id and b.wa_token)
    without_wa = len(branches) - with_wa

    # AI command logs last 24h
    logs_24h_r = await db.execute(
        select(func.count(AICommandLog.id)).where(
            AICommandLog.tenant_id == user.tenant_id,
            AICommandLog.created_at >= day_ago,
        )
    )
    logs_24h = logs_24h_r.scalar_one() or 0

    # Failed commands (actions_taken IS NULL = likely failed)
    failed_r = await db.execute(
        select(func.count(AICommandLog.id)).where(
            AICommandLog.tenant_id == user.tenant_id,
            AICommandLog.created_at >= day_ago,
            AICommandLog.actions_taken.is_(None),
        )
    )
    webhook_errors_24h = failed_r.scalar_one() or 0

    # AI token usage this month (messages + ai_command_logs)
    msg_tokens_r = await db.execute(
        select(func.coalesce(func.sum(Message.tokens_used), 0))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .join(Branch, Conversation.branch_id == Branch.id)
        .where(
            Branch.tenant_id == user.tenant_id,
            Message.created_at >= month_start,
            Message.tokens_used.isnot(None),
        )
    )
    msg_tokens = msg_tokens_r.scalar_one() or 0

    cmd_tokens_r = await db.execute(
        select(func.coalesce(func.sum(AICommandLog.tokens_used), 0)).where(
            AICommandLog.tenant_id == user.tenant_id,
            AICommandLog.created_at >= month_start,
            AICommandLog.tokens_used.isnot(None),
        )
    )
    cmd_tokens = cmd_tokens_r.scalar_one() or 0

    # Config alerts: branches without WA credentials
    config_alerts = [
        {"type": "missing_wa_credentials", "branch_id": str(b.id), "branch_name": b.name}
        for b in branches
        if not b.wa_phone_number_id or not b.wa_token
    ]

    return {
        "role": "it",
        "integrations": {
            "total_branches": len(branches),
            "branches_with_wa": with_wa,
            "branches_without_wa": without_wa,
        },
        "ai_command_logs_24h": logs_24h,
        "webhook_errors_24h": webhook_errors_24h,
        "ai_token_usage_month": int(msg_tokens) + int(cmd_tokens),
        "config_alerts": config_alerts,
    }


# ── Helper ────────────────────────────────────────────────────────────────────

def _resolve_branch(branch_id: uuid.UUID | None, user: User) -> uuid.UUID:
    resolved = branch_id or user.branch_id
    if resolved is None:
        raise HTTPException(
            status_code=400,
            detail="branch_id is required for users without an assigned branch",
        )
    return resolved
