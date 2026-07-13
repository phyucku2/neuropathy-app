"""Application settings, loaded from environment / .env (never hard-coded secrets).

Security-sensitive values are validated at load time and fail CLOSED: a configured
ops bootstrap token shorter than the minimum, or a malformed secret-store key, stops
the process with a clear error instead of booting into a weaker posture (ADR-0017).
"""

from __future__ import annotations

from cryptography.fernet import Fernet
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ops bootstrap tokens shorter than this are refused at startup (ADR-0017): a short
# token would make the constant-time compare in routes/clinic.py guard a guessable
# value. 32 chars of a generated token ≈ 190+ bits from token_urlsafe.
OPS_BOOTSTRAP_TOKEN_MIN_LENGTH = 32


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

    # Ops bootstrap for provisioning clinician accounts (ADR-0012): clinicians are
    # never self-registered (ADR-0010). Unset (the default) means the endpoint fails
    # closed — no token, no provisioning. A configured token must be at least
    # OPS_BOOTSTRAP_TOKEN_MIN_LENGTH chars (validated below); generate one with e.g.
    # `python -c "import secrets; print(secrets.token_urlsafe(48))"` (ADR-0017).
    ops_bootstrap_token: str | None = None

    # Encryption key for the DB-backed OAuth token vault (ADR-0017): a base64 Fernet
    # key, generated with
    # `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
    # Unset (the default) keeps EMR tokens in the per-process in-memory vault even in
    # DB mode — fail closed: secrets are NEVER written to the database unencrypted.
    secret_store_key: str | None = None

    # OAuth pending-auth states (the SMART connect->callback handshake) expire after
    # this many seconds; expired states are rejected and purged (ADR-0017).
    pending_auth_ttl_seconds: int = 600

    # Invitation rate limiting (ADR-0012 deferral -> ADR-0017): at most
    # invite_rate_limit_max accepted invitations per clinician per sliding window.
    invite_rate_limit_max: int = 20
    invite_rate_limit_window_seconds: int = 3600

    # SMART on FHIR / EMR pull (ADR-0008). Client secret (if any) and OAuth tokens live
    # in a secret manager, never here.
    smart_client_id: str | None = None
    smart_redirect_uri: str | None = None
    smart_scopes: str = "launch/patient patient/Observation.read openid fhirUser offline_access"

    # BioMech PDF ingest (ADR-0014). Guards on the text-layer extractor: an upload
    # larger than the byte cap, or with more pages than the page cap, is rejected as a
    # typed error (-> 422) before parsing. Extraction reads the text layer only and
    # never renders or executes anything in the document.
    biomech_max_pdf_bytes: int = 10 * 1024 * 1024  # ~10 MB
    biomech_max_pdf_pages: int = 30
    # Bounds EXTRACTED text, not file size: a small PDF can decompress to
    # gigabytes of text (decompression bomb — ADR-0014 review finding).
    biomech_max_pdf_text_chars: int = 5_000_000

    @field_validator("ops_bootstrap_token", "secret_store_key", mode="before")
    @classmethod
    def _empty_env_is_unset(cls, value: object) -> object:
        """An empty env var means "not configured", never a zero-length credential."""
        return None if value == "" else value

    @field_validator("ops_bootstrap_token")
    @classmethod
    def _bootstrap_token_min_length(cls, value: str | None) -> str | None:
        """Fail closed at startup: a short bootstrap token is a guessable ops gate."""
        if value is not None and len(value) < OPS_BOOTSTRAP_TOKEN_MIN_LENGTH:
            raise ValueError(
                f"OPS_BOOTSTRAP_TOKEN must be at least {OPS_BOOTSTRAP_TOKEN_MIN_LENGTH} "
                "characters; generate one with "
                '`python -c "import secrets; print(secrets.token_urlsafe(48))"` '
                "or leave it unset to disable clinician provisioning entirely"
            )
        return value

    @field_validator("secret_store_key")
    @classmethod
    def _secret_store_key_is_a_fernet_key(cls, value: str | None) -> str | None:
        """Fail closed at startup: a malformed key would surface as undecryptable
        tokens (or worse, tempt a plaintext fallback) at request time."""
        if value is not None:
            try:
                Fernet(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    "SECRET_STORE_KEY must be a base64 Fernet key; generate one with "
                    '`python -c "from cryptography.fernet import Fernet; '
                    'print(Fernet.generate_key().decode())"`'
                ) from exc
        return value


settings = Settings()
