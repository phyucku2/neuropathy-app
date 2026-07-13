"""FastAPI application entrypoint — app factory + DB lifespan wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.db.session import create_engine_and_sessionmaker


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
    application = FastAPI(
        title="neuropathy-app backend",
        version="0.1.0",
        debug=settings.app_debug,
        lifespan=_lifespan,
    )
    application.include_router(api_router)

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "neuropathy-app backend", "env": settings.app_env}

    return application


app = create_app()
