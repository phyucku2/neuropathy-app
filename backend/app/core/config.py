"""Application settings, loaded from environment / .env (never hard-coded secrets)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_debug: bool = False

    database_url: str = "postgresql+asyncpg://neuro:neuro@localhost:5432/neuropathy"

    # External providers — must be BAA-covered before any PHI flows (ADR-0003).
    ai_provider: str | None = None
    ai_api_key: str | None = None
    ocr_provider: str | None = None

    jwt_secret: str | None = None


settings = Settings()
