"""Application settings, loaded from environment / .env (never hard-coded secrets)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_debug: bool = False

    # Persistence is opt-in: set DATABASE_URL to run every request against
    # Postgres-backed repositories in a request-scoped transaction (app/db/session.py,
    # app/api/deps.py). Unset (the default) means the in-memory stores serve requests —
    # per-process and non-durable, for unit tests and DB-less development only.
    # Alembic reads this too; apply migrations before first boot (backend/README.md).
    database_url: str | None = None

    # External providers — must be BAA-covered before any PHI flows (ADR-0003).
    ai_provider: str | None = None
    ai_api_key: str | None = None
    # Explicit operator attestation that a BAA covers the AI provider account.
    # The narrative layer stays OFF without it, even with a key (ADR-0011).
    ai_baa_confirmed: bool = False
    ai_model: str = "claude-haiku-4-5-20251001"
    ocr_provider: str | None = None

    jwt_secret: str | None = None

    # SMART on FHIR / EMR pull (ADR-0008). Client secret (if any) and OAuth tokens live
    # in a secret manager, never here.
    smart_client_id: str | None = None
    smart_redirect_uri: str | None = None
    smart_scopes: str = "launch/patient patient/Observation.read openid fhirUser offline_access"


settings = Settings()
