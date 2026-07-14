"""Async engine/session factories and the request-scoped session dependency.

When `settings.database_url` is configured, the FastAPI lifespan (app/main.py) builds
one engine + sessionmaker per process and parks them on `app.state`. `get_db_session`
then yields one `AsyncSession` per request inside a transaction: commit on success,
rollback on any exception (repositories flush but never commit — the request owns the
transaction boundary). Without a configured database the dependency yields None and
the providers in app/api/deps.py fall back to the in-memory singletons.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Cap on asyncpg connection *establishment* (TCP connect + Postgres handshake). asyncpg's
# default is 60s; a network-partitioned DB would otherwise make every new connection —
# and the /readyz probe that opens one — hang for ~a minute. This bounds establishment
# only (not query execution or waiting for a pool slot, which pool_timeout covers), so it
# is generous enough never to fail a healthy connection under load (ADR-0018 §3).
_CONNECT_TIMEOUT_SECONDS = 5


def create_engine_and_sessionmaker(
    url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """One engine (connection pool) + sessionmaker for the life of the process."""
    # Pool sized for request transactions that (today) span external EMR I/O on some
    # routes — see the deployment note in backend/README.md; session-per-phase is the
    # follow-up that removes that coupling.
    engine = create_async_engine(
        url,
        echo=settings.app_debug,
        future=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=5,
        connect_args={"timeout": _CONNECT_TIMEOUT_SECONDS},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession | None]:
    """Request-scoped session: one transaction per request, or None when no DB.

    FastAPI caches this dependency per request, so every service in one request
    shares the same session/transaction (e.g. the trajectory read and its audit
    event commit or roll back together).
    """
    maker: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "db_sessionmaker", None
    )
    if maker is None:
        if settings.database_url:
            # Fail CLOSED: a configured database with no sessionmaker means the
            # lifespan never ran (mounted sub-app, misbehaving ASGI host). Serving
            # PHI from silent in-memory fallback would lose data on restart
            # (review finding) — refuse instead.
            raise RuntimeError(
                "DATABASE_URL is configured but the app lifespan did not initialize "
                "the database — refusing to fall back to non-durable storage"
            )
        yield None
        return
    async with maker() as session, session.begin():
        yield session
