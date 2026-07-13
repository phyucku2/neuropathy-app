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


def create_engine_and_sessionmaker(
    url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """One engine (connection pool) + sessionmaker for the life of the process."""
    engine = create_async_engine(url, echo=settings.app_debug, future=True)
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
        yield None
        return
    async with maker() as session, session.begin():
        yield session
