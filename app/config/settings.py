from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://flowforge:flowforge_dev_password@localhost:5432/flowforge"

    # ── Redis / ARQ ───────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT ───────────────────────────────────────────────────────────────────
    SECRET_KEY: str = "changeme-replace-with-a-strong-random-secret-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ── Fernet encryption (credentials) ──────────────────────────────────────
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = "changeme-generate-a-real-fernet-key-before-use-32b="

    # ── Integrations (optional — phase 2+) ───────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/google/callback"

    TELEGRAM_BOT_TOKEN: str = ""

    FLOWFORGE_ML_URL: str = "http://localhost:8001"

    # ── App ───────────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    APP_VERSION: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — call this everywhere instead of Settings()."""
    return Settings()
