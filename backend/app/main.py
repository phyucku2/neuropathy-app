"""FastAPI application entrypoint — app factory + DB lifespan wiring."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.deps import get_error_reporter
from app.api.router import api_router
from app.core.config import configured_worker_count, settings
from app.core.errors import ErrorReportingMiddleware
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.metrics import MetricsMiddleware
from app.db.session import create_engine_and_sessionmaker

_log = logging.getLogger(__name__)

# Multipart framing allowance on top of the PDF byte cap for the upload route's
# declared-size check.
_UPLOAD_OVERHEAD_BYTES = 64 * 1024


def _check_serving_secrets() -> None:
    """Guard the serving secrets on the SERVING startup path only (sweep #5; §1B C1).

    Placed in the app lifespan — NOT in Settings construction — so that migration/tooling
    that legitimately has DATABASE_URL but no JWT_SECRET (alembic never signs a token) is
    unaffected; only a request-serving app reaches here.

    JWT_SECRET: in the durable (Postgres) MULTI-WORKER deployment a missing JWT_SECRET is
    a hard fail: each gunicorn worker would fall back to its own random ephemeral key
    (deps._process_jwt_secret), so a token issued by worker A fails verification on
    worker B — an intermittent, hard-to-diagnose 401 / session-expiry storm. Fail fast
    there. A single-process DB deployment (one worker) can still run on the ephemeral key
    within that process, so it only WARNS.

    SECRET_STORE_KEY (readiness plan §1B C1): same scoping, same rationale. Without the
    key, DB mode keeps every vaulted secret (EMR OAuth tokens, MFA TOTP secrets) in a
    PER-PROCESS in-memory vault — fail closed, never plaintext (ADR-0017) — so under
    multiple workers a secret vaulted by worker A is invisible to worker B and everything
    vanishes on restart. That silent non-durability is a hard fail in the multi-worker
    deployment; a single-process DB deployment WARNS (here, at boot — deps._process_fernet
    no longer re-warns at request time, so the posture is stated exactly once)."""
    if not settings.database_url:
        return
    multi_worker = configured_worker_count() > 1
    if not settings.jwt_secret:
        if multi_worker:
            raise RuntimeError(
                "JWT_SECRET must be set when DATABASE_URL is configured and WEB_CONCURRENCY > 1 "
                "(multi-worker deployment): without it each worker signs tokens with a different "
                "ephemeral key, so a token issued by one worker fails verification on another "
                "(intermittent 401 / session-expiry storm). Generate one with "
                '`python -c "import secrets; print(secrets.token_urlsafe(48))"`. '
                "Rotating it later logs everyone out."
            )
        _log.warning(
            "JWT_SECRET is not set in DB mode; falling back to a per-process ephemeral signing "
            "key. Tokens will not survive a restart, and this is UNSAFE if you scale past one "
            "worker (WEB_CONCURRENCY > 1). Set JWT_SECRET for durable, multi-worker sessions."
        )
    if not settings.secret_store_key:
        if multi_worker:
            raise RuntimeError(
                "SECRET_STORE_KEY must be set when DATABASE_URL is configured and "
                "WEB_CONCURRENCY > 1 (multi-worker deployment): without it vaulted secrets "
                "(EMR OAuth tokens, MFA TOTP secrets) stay in a per-process in-memory vault — "
                "invisible to sibling workers and lost on every restart. Generate one with "
                '`python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"`. '
                "Plaintext secrets are never written to the database."
            )
        _log.warning(
            "SECRET_STORE_KEY is not configured: vaulted secrets (EMR OAuth tokens, MFA TOTP "
            "secrets) stay in the per-process in-memory vault and will not survive a restart "
            "or reach other workers. Configure the key to enable the encrypted DB vault "
            "(ADR-0017); plaintext secrets are never written to the database."
        )


def _check_serving_config() -> None:
    """Refuse to SERVE with APP_DEBUG on in a real deployment (readiness plan §1B C4).

    Debug mode turns on FastAPI/Starlette debug tracebacks (per-frame locals — raw PHI in
    an error page) and SQL echo. Same scoping and same lifespan placement as
    _check_serving_secrets: DB mode + multi-worker is a hard fail; a single-process DB
    deployment WARNS (dev against a local database is legitimate); tooling and the
    in-memory test/dev mode are untouched."""
    if not (settings.app_debug and settings.database_url):
        return
    if configured_worker_count() > 1:
        raise RuntimeError(
            "APP_DEBUG must be off when DATABASE_URL is configured and WEB_CONCURRENCY > 1 "
            "(multi-worker deployment): debug error pages render per-frame locals — raw "
            "request values and PHI — to the client, and SQL echo prints query parameters "
            "into the logs. Unset APP_DEBUG (or set it to false) for any real deployment."
        )
    _log.warning(
        "APP_DEBUG is on in DB mode: debug tracebacks expose per-frame locals (raw PHI) "
        "and SQL echo prints query parameters. Never serve real data like this; unset "
        "APP_DEBUG before scaling past one worker."
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the process-wide engine/sessionmaker when DATABASE_URL is configured.

    The schema is owned by Alembic and applied by a human (`alembic upgrade head`,
    files-only rule — see backend/README.md) before first boot: the app never creates
    or migrates tables itself. With no DATABASE_URL the sessionmaker stays None and
    every request runs on the in-memory stores (app/api/deps.py).
    """
    if settings.database_url is None:
        app.state.db_sessionmaker = None
        yield
        return
    _check_serving_secrets()
    _check_serving_config()
    engine, sessionmaker = create_engine_and_sessionmaker(settings.database_url)
    app.state.db_engine = engine
    app.state.db_sessionmaker = sessionmaker
    try:
        yield
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    """Application factory — tests boot isolated instances to simulate restarts."""
    configure_logging(debug=settings.app_debug)
    application = FastAPI(
        title="neuropathy-app backend",
        version="0.1.0",
        debug=settings.app_debug,
        lifespan=_lifespan,
    )
    application.include_router(api_router)

    @application.exception_handler(RequestValidationError)
    async def _validation_error_without_input_echo(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """422 bodies must never echo the submitted value (readiness plan §1B C3).

        FastAPI's default handler serializes ``exc.errors()`` whole, and every entry
        carries an ``input`` key — the raw submitted value (a mistyped email, a password
        sent in the wrong field, a lab value). ``ctx`` can embed the error's context
        objects the same way. Strip both and keep only the safe, fixed-shape fields the
        client actually needs to render a field error; ``hide_input_in_errors`` on the
        schemas (app/schemas/base.py) keeps the same values out of the *logged* message.
        """
        detail = [
            {key: value for key, value in error.items() if key in ("type", "loc", "msg")}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": detail})

    @application.middleware("http")
    async def _reject_oversized_uploads(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Refuse an over-declared upload BEFORE its body is parsed or spooled — the
        PDF byte cap must bound network/disk work, not just memory (ADR-0014 review
        finding). A chunked request without Content-Length still spools to disk; the
        route's `file.size` check and bounded read then cap what reaches memory.
        """
        if request.url.path == "/biomech/reports":
            declared = request.headers.get("content-length", "")
            if declared.isdigit() and (
                int(declared) > settings.biomech_max_pdf_bytes + _UPLOAD_OVERHEAD_BYTES
            ):
                return JSONResponse(
                    status_code=422,
                    content={"detail": "Upload exceeds the PDF size cap"},
                )
        return await call_next(request)

    # Middleware onion, outermost → innermost (Starlette wraps the LAST-added around all
    # earlier ones, so these are registered in reverse of the desired nesting):
    #
    #   RequestLoggingMiddleware  (outermost — MUST stay index 0, ADR-0018 §4)
    #     └─ MetricsMiddleware      (counts every request incl. 5xx; PHI-free labels)
    #         └─ ErrorReportingMiddleware  (forwards scrubbed unhandled-exception events)
    #             └─ _reject_oversized_uploads  (inner upload guard, added first above)
    #
    # ErrorReporting sits inside metrics/logging but OUTSIDE the router, so it catches an
    # unhandled exception, emits its ONE scrubbed event, and CONTAINS it (readiness plan
    # §1B C3): it returns the static PHI-free 500 body instead of re-raising, so the
    # exception message — which can echo request values — never reaches uvicorn.error or
    # the ASGI server's traceback rendering. Metrics and logging then see an ordinary 500
    # response on their normal paths (one log line, one count — the ADR-0018/0021
    # invariants hold unchanged). Logging stays outermost so even an upload-guard
    # short-circuit is logged with an X-Request-ID (ADR-0018 §4) — the `is-outermost`
    # test still holds.
    application.add_middleware(
        ErrorReportingMiddleware,
        reporter_factory=get_error_reporter,
        env=settings.app_env,
    )
    application.add_middleware(MetricsMiddleware)
    application.add_middleware(RequestLoggingMiddleware)

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "neuropathy-app backend", "env": settings.app_env}

    return application


app = create_app()
