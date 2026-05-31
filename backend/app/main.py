import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, branches, kb, leads, onboarding, webhooks
from app.api.users import team_router, users_router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Walix Backend",
    description="Conversational CRM with WhatsApp for Mexican SMBs",
    version="0.1.0",
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


app.include_router(auth.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(branches.router, prefix="/api")
app.include_router(team_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(kb.router, prefix="/api")
app.include_router(onboarding.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "walix-backend", "env": settings.APP_ENV}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
