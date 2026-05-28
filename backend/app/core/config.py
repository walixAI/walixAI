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

    @property
    def effective_database_url(self) -> str:
        # Railway's internal hostname (.railway.internal) only resolves inside
        # Railway's network. Locally prefer the public proxy URL.
        if self.APP_ENV == "development" and self.DATABASE_PUBLIC_URL:
            return self.DATABASE_PUBLIC_URL
        return self.DATABASE_URL


settings = Settings()
