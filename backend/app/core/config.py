"""Application settings, loaded from environment / .env (never hard-coded secrets).

Security-sensitive values are validated at load time and fail CLOSED: a configured
ops bootstrap token shorter than the minimum, or a malformed secret-store key, stops
the process with a clear error instead of booting into a weaker posture (ADR-0017).
The error never echoes the rejected value (`hide_input_in_errors`): startup failures
land in boot-loop logs, and a nearly-valid secret printed there is still a secret.
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
    # hide_input_in_errors: a rejected value must NEVER be echoed back — pydantic's
    # default ValidationError rendering appends `input_value=...`, which would print a
    # too-short OPS_BOOTSTRAP_TOKEN or a mistyped SECRET_STORE_KEY verbatim into
    # boot-loop logs (ADR-0017 review finding).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

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

    # FIRST-OPS bootstrap token (ADR-0019 narrows ADR-0012/0017's role). It no longer
    # gates clinician provisioning — that now requires a real ops bearer (require_ops).
    # Its ONLY remaining power is creating the FIRST ops account via POST /ops/accounts
    # while zero ops accounts exist; the moment any ops account exists this token opens
    # nothing (the gate self-closes and further operators are created by an
    # authenticated ops). Unset (the default) means no ops can be bootstrapped and — with
    # no ops accounts — no provisioning is possible either: fail closed. A configured
    # token must be at least OPS_BOOTSTRAP_TOKEN_MIN_LENGTH chars (validated below);
    # generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
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

    # Account-deletion password throttle (ADR-0027): failed fresh re-auth attempts on
    # DELETE /auth/me are audited ('account_delete_denied') and capped per actor — at
    # most delete_account_rate_limit_max failures per sliding window. Over the budget
    # the endpoint answers 429 BEFORE the Argon2id verify even runs, so the limiter
    # caps both the password oracle and its CPU cost; the cap equally bounds the
    # denial audit volume (no log-flood primitive).
    delete_account_rate_limit_max: int = 5
    delete_account_rate_limit_window_seconds: int = 900

    # Bootstrap-denial audit cap (ADR-0017): failed attempts on the UNAUTHENTICATED
    # provisioning gate are audited, but at most bootstrap_denied_audit_max rows per
    # sliding window — beyond the cap the 403 is unchanged and only the audit write is
    # skipped, so an anonymous client cannot flood the audit table with denial rows.
    bootstrap_denied_audit_max: int = 20
    bootstrap_denied_audit_window_seconds: int = 3600

    # Error reporting seam (ADR-0021). OFF by default: unset means unhandled exceptions
    # are never forwarded anywhere. When set to a self-hosted, permissive collector URL
    # (e.g. a GlitchTip/Sentry-compatible or plain HTTP intake you run under a BAA), the
    # app POSTs a PHI-SCRUBBED error event (exception type, route template, request id,
    # status, timestamp — never the exception message, query, body, headers, or patient
    # data). A reporter error never breaks the request (fail-safe). NEVER a SaaS DSN with
    # an embedded token committed here — this is a config env var, resolved at runtime.
    error_reporting_dsn: str | None = None
    # Upper bound on the fire-and-forget POST to the collector; kept short so a slow or
    # wedged collector can never drag an already-failed request.
    error_reporting_timeout_seconds: float = 3.0

    # SMART on FHIR / EMR pull (ADR-0008). Client secret (if any) and OAuth tokens live
    # in a secret manager, never here.
    #
    # Client ids are PER VENDOR (ADR-0028; each EMR issues its own at registration):
    # every provider-registry entry (app/emr/providers.py) names its field below via
    # `client_id_env`, and the generic `smart_client_id` is the fallback for custom
    # fhir_base connections and providers with no specific id configured. Client ids
    # are low-sensitivity but stay env-driven — values are never committed.
    smart_client_id: str | None = None
    smart_client_id_epic: str | None = None
    smart_client_id_oracle_health: str | None = None
    smart_client_id_athenahealth: str | None = None
    smart_client_id_meditech: str | None = None
    smart_client_id_nextgen: str | None = None
    smart_client_id_veradigm: str | None = None
    smart_redirect_uri: str | None = None
    # NOTE: the former `smart_scopes` setting was removed (ADR-0028): nothing ever read
    # it, so an operator changing SMART_SCOPES would have changed nothing — the same
    # false promise the enforced-flag rule exists to prevent (docs/lessons.md). The
    # requested scope set is code: DEFAULT_SCOPES in app/emr/smart.py.

    # BioMech PDF ingest (ADR-0014). Guards on the text-layer extractor: an upload
    # larger than the byte cap, or with more pages than the page cap, is rejected as a
    # typed error (-> 422) before parsing. Extraction reads the text layer only and
    # never renders or executes anything in the document.
    biomech_max_pdf_bytes: int = 10 * 1024 * 1024  # ~10 MB
    biomech_max_pdf_pages: int = 30
    # Bounds EXTRACTED text, not file size: a small PDF can decompress to
    # gigabytes of text (decompression bomb — ADR-0014 review finding).
    biomech_max_pdf_text_chars: int = 5_000_000

    @field_validator(
        "ops_bootstrap_token", "secret_store_key", "error_reporting_dsn", mode="before"
    )
    @classmethod
    def _empty_env_is_unset(cls, value: object) -> object:
        """An empty env var means "not configured", never a zero-length credential.

        For ``error_reporting_dsn`` this keeps the seam fail-safe OFF when the env var is
        present-but-blank, exactly as an absent var does."""
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
