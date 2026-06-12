import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import activities, agents, ai, auth, automations, branches, contacts, dashboard, health, kb, leads, metrics, onboarding, pipeline, platform, support, tags, webhooks
from app.api.users import team_router, users_router
from app.middleware.tenant_context import TenantContextMiddleware
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
origins = []
if settings.FRONTEND_URL:
    origins = [o.strip().rstrip("/") for o in settings.FRONTEND_URL.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # Permite cualquier preview/deploy de Vercel del proyecto walix
    allow_origin_regex=r"https://walix[a-z0-9\-]*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# TenantContextMiddleware runs as the outermost layer (last added = first to
# run). It sets request.state.tenant_id from the JWT so that get_db can call
# set_config before any query. Requests without a JWT get NULL_UUID (safe).
app.add_middleware(TenantContextMiddleware)


app.include_router(agents.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
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
app.include_router(contacts.router, prefix="/api")
app.include_router(activities.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(health.router)  # /health — no prefix, used by deploy smoke tests


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "walix-backend", "env": settings.APP_ENV}
