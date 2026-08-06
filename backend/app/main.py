import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import activities, agents, ai, ai_copilot, auth, automations, billing, billing_webhook, branches, contacts, dashboard, dashboard_widgets, deals, finance, goals, health, kb, leads, message_templates, metrics, onboarding, pipeline, pipelines, platform, profitability, saved_views, support, tags, tasks, tenant, walix_builder, webhooks
from app.api.industry_onboarding import onboarding_router as industry_onboarding_router
from app.api.industry_onboarding import settings_router as industry_settings_router
from app.api.users import team_router, users_router
from app.middleware.tenant_context import TenantContextMiddleware
from app.middleware.trial_guard import TrialGuardMiddleware
from app.services.scheduler import lifespan_scheduler
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Temporary file handler for diagnosis
_fh = logging.FileHandler("/tmp/walix_debug.log")
_fh.setLevel(logging.INFO)
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger("app").addHandler(_fh)

app = FastAPI(
    title="Walix Backend",
    description="Conversational CRM with WhatsApp for Mexican SMBs",
    version="0.1.0",
    lifespan=lifespan_scheduler,
)

# FRONTEND_URL puede ser una lista separada por comas; limpiamos espacios y diagonales finales
_KNOWN_ORIGINS = [
    "https://walix-ai.vercel.app",
    "https://walix.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
]
origins = list(_KNOWN_ORIGINS)
if settings.FRONTEND_URL:
    for o in settings.FRONTEND_URL.split(","):
        cleaned = o.strip().rstrip("/")
        if cleaned and cleaned not in origins:
            origins.append(cleaned)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # Permite previews de Vercel: walix-*.vercel.app
    allow_origin_regex=r"https://walix[a-z0-9-]*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# TenantContextMiddleware runs as the outermost layer (last added = first to
# run). It sets request.state.tenant_id from the JWT so that get_db can call
# set_config before any query. Requests without a JWT get NULL_UUID (safe).
# Middleware execution order (LIFO: last added = outermost = runs first):
#   1. TenantContextMiddleware  → decodes JWT, sets request.state.tenant_id
#   2. TrialGuardMiddleware     → reads tenant_id set by step 1, checks trial expiry
# Adding TrialGuard first makes it inner (runs after TenantContext).
app.add_middleware(TrialGuardMiddleware)
app.add_middleware(TenantContextMiddleware)


app.include_router(agents.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(ai_copilot.router, prefix="/api")  # C4: /api/ai/copilot/*
app.include_router(auth.router, prefix="/api")
app.include_router(automations.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(branches.router, prefix="/api")
app.include_router(team_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(kb.router, prefix="/api")
app.include_router(onboarding.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(platform.router, prefix="/api")
app.include_router(support.router, prefix="/api")
app.include_router(leads.tasks_router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(metrics.pipeline_router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")
app.include_router(saved_views.router, prefix="/api")  # must precede contacts (avoids /{contact_id} collision)
app.include_router(contacts.router, prefix="/api")
app.include_router(activities.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(industry_onboarding_router, prefix="/api")  # Sprint 8B: /api/v1/onboarding/*
app.include_router(industry_settings_router, prefix="/api")    # Sprint 8B: /api/v1/settings/*
app.include_router(tenant.router, prefix="/api")               # Sprint 9: /api/tenant/*
app.include_router(auth.v2_router, prefix="/api")              # Sprint 9: /api/v2/auth/*
app.include_router(billing.router, prefix="/api")              # Sprint 10: /api/v1/billing/*
app.include_router(billing_webhook.router, prefix="/api")      # Sprint 10: /api/webhooks/stripe
app.include_router(deals.router, prefix="/api")                # Sprint 13A: /api/deals
app.include_router(pipelines.router, prefix="/api")            # multi-pipeline CRUD
app.include_router(tasks.router, prefix="/api")                # Etapa 5: /api/tasks/*
app.include_router(finance.router, prefix="/api")              # Metas/Gastos
app.include_router(goals.router, prefix="/api")                # Metas Gen2
app.include_router(profitability.router, prefix="/api")        # Rentabilidad / run-rate
app.include_router(walix_builder.router, prefix="/api")        # B2: /api/ai/builder/*
app.include_router(message_templates.branch_templates_router, prefix="/api")
app.include_router(message_templates.templates_router, prefix="/api")
app.include_router(dashboard_widgets.widgets_router, prefix="/api")
app.include_router(health.router)  # /health — no prefix, used by deploy smoke tests


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "walix-backend", "env": settings.APP_ENV}
