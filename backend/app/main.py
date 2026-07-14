"""FastAPI application entrypoint — app factory + DB lifespan wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import RequestLoggingMiddleware, configure_logging
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

    # Registered LAST so Starlette makes it the OUTERMOST middleware (the last-added
    # middleware wraps all earlier ones): it times the whole request and logs one
    # PHI-free JSON line — including responses short-circuited by the upload guard above,
    # which must still produce a log line and an X-Request-ID header (ADR-0018 §4).
    application.add_middleware(RequestLoggingMiddleware)

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "neuropathy-app backend", "env": settings.app_env}

    return application


app = create_app()
