from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    DATABASE_URL: str
    DATABASE_PUBLIC_URL: str | None = None
    # Conexión de solo-migraciones (rol admin/superuser). Opcional: mientras
    # no esté seteada, effective_alembic_database_url cae a
    # effective_database_url (comportamiento actual, sin cambios). Una vez
    # que DATABASE_URL/DATABASE_PUBLIC_URL se repunten a walix_app (sin
    # bypass de RLS) en Railway, Alembic necesita seguir corriendo con un rol
    # con privilegios de DDL — ver scripts/setup_db_user.py.
    ALEMBIC_DATABASE_URL: str | None = None
    ALEMBIC_DATABASE_PUBLIC_URL: str | None = None
    ANTHROPIC_API_KEY: str
    # Verify Token: arbitrary string echoed during webhook setup (GET handshake).
    # Pick any value, set it both here and in Meta's webhook UI.
    META_VERIFY_TOKEN: str
    # App Secret: Meta-generated value used to validate the HMAC-SHA256 signature
    # on POST webhooks. Found at Meta dashboard → Settings → Basic → App Secret.
    META_APP_SECRET: str
    REDIS_URL: str
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_HOST: str = "https://us.cloud.langfuse.com"
    APP_ENV: str = "development"
    SECRET_KEY: str
    FRONTEND_URL: str = "http://localhost:3000"
    # OpenAI — solo requerido para scripts/ingest_kb.py
    OPENAI_API_KEY: str | None = None

    # Internal Walix WA number — commands from Walix staff phones go here
    WALIX_INTERNAL_WA_NUMBER_ID: str | None = None
    WALIX_INTERNAL_WA_TOKEN: str | None = None

    # ── Stripe (Sprint 10 — Billing) ──────────────────────────────────────────
    # Use sk_test_... in development, sk_live_... in production.
    # All Stripe vars are optional so the app starts without billing configured.
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_STARTER: str | None = None
    STRIPE_PRICE_GROWTH: str | None = None
    STRIPE_PRICE_BUSINESS: str | None = None

    @property
    def effective_database_url(self) -> str:
        # Railway's internal hostname (.railway.internal) only resolves inside
        # Railway's network. Locally prefer the public proxy URL.
        #
        # Esta es la conexión de RUNTIME de la app (FastAPI, background
        # tasks). Está pensada para terminar apuntando al rol walix_app
        # (sin BYPASSRLS) una vez que Railway actualice estas variables a
        # mano — ver scripts/setup_db_user.py. Hoy sigue apuntando al rol
        # admin hasta que se haga ese cambio coordinado.
        if self.APP_ENV == "development" and self.DATABASE_PUBLIC_URL:
            return self.DATABASE_PUBLIC_URL
        return self.DATABASE_URL

    @property
    def effective_alembic_database_url(self) -> str:
        # Conexión SOLO para Alembic (migraciones/DDL) — debe ser un rol
        # admin/superuser, nunca walix_app (que no tiene permisos de DDL a
        # propósito). Si ALEMBIC_DATABASE_URL(_PUBLIC) no está seteada, cae a
        # effective_database_url: esto mantiene el comportamiento actual sin
        # romper nada hasta que Railway separe las dos variables.
        if self.APP_ENV == "development" and self.ALEMBIC_DATABASE_PUBLIC_URL:
            return self.ALEMBIC_DATABASE_PUBLIC_URL
        if self.ALEMBIC_DATABASE_URL:
            return self.ALEMBIC_DATABASE_URL
        return self.effective_database_url


settings = Settings()
