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

    # SMART on FHIR / EMR pull (ADR-0008). Client secret (if any) and OAuth tokens live
    # in a secret manager, never here.
    smart_client_id: str | None = None
    smart_redirect_uri: str | None = None
    smart_scopes: str = "launch/patient patient/Observation.read openid fhirUser offline_access"


settings = Settings()
