"""Application settings, loaded from environment / .env (never hard-coded secrets).

Security-sensitive values are validated at load time and fail CLOSED: a configured
ops bootstrap token shorter than the minimum, or a malformed secret-store key, stops
the process with a clear error instead of booting into a weaker posture (ADR-0017).
The error never echoes the rejected value (`hide_input_in_errors`): startup failures
land in boot-loop logs, and a nearly-valid secret printed there is still a secret.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ops bootstrap tokens shorter than this are refused at startup (ADR-0017): a short
# token would make the constant-time compare in routes/clinic.py guard a guessable
# value. 32 chars of a generated token ≈ 190+ bits from token_urlsafe.
OPS_BOOTSTRAP_TOKEN_MIN_LENGTH = 32


def configured_worker_count() -> int:
    """The gunicorn worker count for this deployment, from WEB_CONCURRENCY (Dockerfile /
    the standard gunicorn env var). Unset or unparseable → 1 (single process: the test
    harness, `uvicorn` dev, `WEB_CONCURRENCY=1`).

    Read from os.environ at CALL time — never captured into a Settings field — so the
    serving guards (app/main.py) and the TLS auto-mode (app/db/session.py) see the env
    the process actually runs with, not the one at import time."""
    try:
        return max(1, int(os.environ.get("WEB_CONCURRENCY", "1")))
    except ValueError:
        return 1


class Settings(BaseSettings):
    # hide_input_in_errors: a rejected value must NEVER be echoed back — pydantic's
    # default ValidationError rendering appends `input_value=...`, which would print a
    # too-short OPS_BOOTSTRAP_TOKEN or a mistyped SECRET_STORE_KEY verbatim into
    # boot-loop logs (ADR-0017 review finding).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: str = "local"
    app_debug: bool = False

    # Cross-origin allow-list for the NATIVE mobile shells only (ADR-0023). The web app is
    # served same-origin (nginx reverse-proxies the API, so no CORS is needed or wanted).
    # The Capacitor WebView, however, loads the bundled SPA from a fixed local origin —
    # `https://localhost` on Android, `capacitor://localhost` on iOS — and calls the API
    # cross-origin, so those two exact origins (and no wildcard) are allow-listed. A browser
    # page cannot forge these origins, so only the real native app is admitted. Comma-separated;
    # set empty to disable CORS entirely (e.g. a strictly web-only deployment).
    mobile_app_origins: str = "https://localhost,capacitor://localhost"

    # Persistence is opt-in: set DATABASE_URL to run every request against
    # Postgres-backed repositories in a request-scoped transaction (app/db/session.py,
    # app/api/deps.py). Unset (the default) means the in-memory stores serve requests —
    # per-process and non-durable, for unit tests and DB-less development only.
    # Alembic reads this too; apply migrations before first boot (backend/README.md).
    database_url: str | None = None

    # Postgres TLS enforcement (readiness plan §1B C2), applied lexically to
    # DATABASE_URL when the serving engine is created (app/db/session.py) — alembic and
    # the integration suite build their own engines and are structurally unaffected.
    # Tri-state:
    #   None (default) = AUTO — TLS is required when this deployment is really serving
    #     (WEB_CONCURRENCY > 1, read at engine-creation time) or app_env=production;
    #   True  = always required;
    #   False = the DOCUMENTED opt-out for local dev / tests against a plaintext local
    #     Postgres (e.g. docker-compose, the TEST_DATABASE_URL integration service).
    #     Never set this in production.
    # "Required" means the URL must carry an ssl/sslmode directive that actually turns
    # TLS on (ssl=require / sslmode=require / verify-ca / verify-full); a missing
    # directive — or ssl=disable/allow/prefer, which can silently downgrade — refuses
    # to boot. verify-full with the platform CA is the recommended production value.
    database_tls_required: bool | None = None

    # External providers — must be BAA-covered before any PHI flows (ADR-0003).
    # ai_provider selects the narrator: unset/"anthropic" → Anthropic Messages API;
    # "azure_openai" (aka "azure") → Azure OpenAI, the HIPAA-eligible path under
    # Microsoft's BAA once Claude is off the PHI layer (ADR-0040).
    ai_provider: str | None = None
    ai_api_key: str | None = None
    # Explicit operator attestation that a BAA covers the AI provider account.
    # The narrative layer stays OFF without it, even with a key (ADR-0011).
    ai_baa_confirmed: bool = False
    # Logical model label — used for BOTH the Anthropic model id AND (provider-neutral)
    # the narrative cache key + disclosure-audit label. For Azure set this to the model
    # behind the deployment (e.g. "gpt-4o") so audits read cleanly.
    ai_model: str = "claude-haiku-4-5-20251001"
    # Azure OpenAI narrator (ADR-0040) — only read when ai_provider is Azure. Azure routes
    # by DEPLOYMENT, not model id. ai_azure_deployment defaults to ai_model when blank.
    ai_azure_endpoint: str | None = None  # e.g. https://<resource>.openai.azure.com
    ai_azure_deployment: str | None = None
    ai_azure_api_version: str = "2024-10-21"  # a GA data-plane version; override as needed
    ocr_provider: str | None = None

    # Visit-Ready Summary (ADR-0045). The change-pointed "questions to ask" edge toward
    # decision support and are HELD for the FDA D2 opinion (ADR-0041, ADR-0045 open
    # question #2): OFF by default, so Phase 1 renders only the clearly-safe
    # data-completeness prompts. Flip ON only after owner/D2 sign-off. Deterministic
    # either way — the flag never routes anything through the AI narrator.
    include_change_questions: bool = False

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

    # Login throttle (readiness plan §1B C5): failed /auth/login attempts are audited
    # ('login_failed') under a per-email-hash sentinel actor and capped per sliding
    # window — over the budget the endpoint answers 429 BEFORE the Argon2id verify (or
    # any repository lookup) runs, so the limiter caps both the password oracle and its
    # CPU cost without ever keying on the raw email (non-enumerating by construction).
    login_rate_limit_max: int = 10
    login_rate_limit_window_seconds: int = 900

    # Refresh throttle (readiness plan §1B C5): failed /auth/refresh attempts on a
    # signature-valid token are audited ('refresh_failed') under a per-subject sentinel
    # actor and capped the same way — 429 before the repository lookup. Generous by
    # default: a healthy client refreshes at most every access-token TTL.
    refresh_rate_limit_max: int = 30
    refresh_rate_limit_window_seconds: int = 3600

    # MFA enforcement flag (readiness plan §1B C6). False (default): clinician/ops
    # accounts WITH a confirmed TOTP factor get the login step-up; unenrolled ones log
    # in exactly as before. True — the go-live act — additionally REFUSES password
    # login for unenrolled clinician/ops principals with an enrollment-required
    # response. Patients are never gated by this flag.
    mfa_required_for_privileged: bool = False

    # Data-export throttle (ADR-0031): GET /me/export runs an unbounded O(n) full-account
    # assembly, so it is capped per actor exactly like deletion. Each successful export
    # writes one 'export_account' audit event, so the sliding window counts those events
    # (the invite-limiter pattern) — at most export_rate_limit_max exports per window.
    # Over the budget the endpoint answers 429 BEFORE assembling anything, bounding both
    # the work and the disclosure/audit volume per patient.
    export_rate_limit_max: int = 10
    export_rate_limit_window_seconds: int = 3600

    # Caregiver invite-claim throttle (ADR-0047, the ADR-0017 sliding-window
    # pattern): claim attempts — the authenticated caregiver claim AND the
    # code-gated self-registration — are capped per actor (user id, or a per-email
    # sentinel for registration) by counting 'caregiver_claim' audit events. Over the
    # budget the answer is 429 BEFORE the code is hashed or looked up, so a refusal
    # reveals nothing about the probed code and a guessing campaign is slowed to the
    # window budget.
    caregiver_claim_rate_limit_max: int = 10
    caregiver_claim_rate_limit_window_seconds: int = 3600

    # Caregiver push notifications (ADR-0047). OFF by default. When True AND a Firebase
    # service-account credential is present, deps selects the REAL FCM HTTP v1 sender
    # (services/push.py); flag on but NO credential — or flag off — fails SAFE to the
    # no-op path (a rolled-back or unconfigured push never reaches a device). Payloads are
    # PHI-free by contract (services/push.py::PushMessage).
    caregiver_push_enabled: bool = False

    # The Firebase service-account JSON (ADR-0047 B2), injected as a secret at runtime —
    # NEVER committed. The raw JSON string; deps parses it and mints the FCM OAuth2 token
    # from it (scope firebase.messaging). Empty/unset falls back to
    # GOOGLE_APPLICATION_CREDENTIALS (a path), then to the no-op path. .env.example
    # carries only a commented placeholder.
    fcm_credentials_json: str | None = None

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
        "jwt_secret",
        "ops_bootstrap_token",
        "secret_store_key",
        "error_reporting_dsn",
        "fcm_credentials_json",
        mode="before",
    )
    @classmethod
    def _empty_env_is_unset(cls, value: object) -> object:
        """An empty env var means "not configured", never a zero-length credential.

        For ``error_reporting_dsn`` this keeps the seam fail-safe OFF when the env var is
        present-but-blank, exactly as an absent var does. For ``jwt_secret`` it makes a
        blank ``JWT_SECRET=`` (common with ``JWT_SECRET: ${JWT_SECRET}`` and the shell var
        unset) read as unset, so the serving-startup guard in app/main.py treats it as
        missing rather than as a zero-length signing key (sweep #5)."""
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
