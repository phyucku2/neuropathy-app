"""FastAPI application entrypoint — app factory + DB lifespan wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.api.deps import get_error_reporter
from app.api.router import api_router
from app.core.config import settings
from app.core.errors import ErrorReportingMiddleware
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.metrics import MetricsMiddleware
from app.db.session import create_engine_and_sessionmaker

# Multipart framing allowance on top of the PDF byte cap for the upload route's
# declared-size check.
_UPLOAD_OVERHEAD_BYTES = 64 * 1024


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
    # unhandled exception on its way to the normal 500 handler and re-raises it unchanged
    # (the client-facing response never changes). Metrics records in a `finally`, so a 5xx
    # is still counted. Logging stays outermost so even an upload-guard short-circuit is
    # logged with an X-Request-ID (ADR-0018 §4) — the `is-outermost` test still holds.
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
