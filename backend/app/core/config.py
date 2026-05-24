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
    META_WHATSAPP_TOKEN: str
    META_PHONE_NUMBER_ID: str
    META_WEBHOOK_SECRET: str
    REDIS_URL: str
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str
    APP_ENV: str = "development"
    SECRET_KEY: str
    FRONTEND_URL: str = "http://localhost:3000"

    @property
    def effective_database_url(self) -> str:
        # Railway's internal hostname (.railway.internal) only resolves inside
        # Railway's network. Locally prefer the public proxy URL.
        if self.APP_ENV == "development" and self.DATABASE_PUBLIC_URL:
            return self.DATABASE_PUBLIC_URL
        return self.DATABASE_URL


settings = Settings()
