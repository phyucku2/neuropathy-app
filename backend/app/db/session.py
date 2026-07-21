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
from urllib.parse import parse_qs, urlsplit

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import configured_worker_count, settings

# Cap on asyncpg connection *establishment* (TCP connect + Postgres handshake). asyncpg's
# default is 60s; a network-partitioned DB would otherwise make every new connection —
# and the /readyz probe that opens one — hang for ~a minute. This bounds establishment
# only (not query execution or waiting for a pool slot, which pool_timeout covers), so it
# is generous enough never to fail a healthy connection under load (ADR-0018 §3).
_CONNECT_TIMEOUT_SECONDS = 5

# ssl/sslmode values that actually turn TLS ON (libpq/asyncpg vocabulary). Anything else
# — disable, allow, prefer (which silently downgrades on a broken TLS handshake), or a
# missing directive — does not satisfy the enforcement below.
_TLS_ON_VALUES = frozenset({"require", "verify-ca", "verify-full", "true", "on"})


def _database_tls_enforced() -> bool:
    """Whether the serving engine must refuse a non-TLS Postgres URL (§1B C2).

    Tri-state setting resolved HERE, at engine-creation time — not as a pydantic field
    default — because the auto mode reads WEB_CONCURRENCY from the live environment
    exactly like the serving guards in app/main.py (a plain bool default captured at
    Settings construction could not see it)."""
    if settings.database_tls_required is not None:
        return settings.database_tls_required
    return configured_worker_count() > 1 or settings.app_env == "production"


def _url_declares_tls(url: str) -> bool:
    """PURELY LEXICAL check that the URL turns TLS on — no connection is ever made.

    The engine (and its pool) is lazy: nothing connects until the first request, and
    the serving lifespan (plus tests booting with synthetic URLs) relies on that. So
    this inspects only the query string: an `ssl` (asyncpg) or `sslmode` (libpq) value
    from the TLS-on vocabulary passes; absent or downgrade values do not."""
    if not urlsplit(url).scheme.startswith("postgresql"):
        return True  # not Postgres (e.g. sqlite in a tool) — nothing to enforce here
    query = parse_qs(urlsplit(url).query)
    declared = [value.lower() for key in ("ssl", "sslmode") for value in query.get(key, [])]
    return any(value in _TLS_ON_VALUES for value in declared)


def create_engine_and_sessionmaker(
    url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """One engine (connection pool) + sessionmaker for the life of the process.

    Called ONLY by the serving lifespan (app/main.py) — alembic/env.py and the
    integration suite call `create_async_engine` directly — so the TLS enforcement
    below is structurally scoped to the request-serving app and can never break
    migrations or the plaintext TEST_DATABASE_URL integration service (§1B C2).
    """
    if _database_tls_enforced() and not _url_declares_tls(url):
        raise RuntimeError(
            "DATABASE_URL must require TLS in this deployment (append ?ssl=require, or "
            "sslmode=verify-full with the platform CA): the URL carries no TLS-on "
            "ssl/sslmode directive, and serving PHI over a plaintext database connection "
            "is refused (readiness plan C2). For local development or tests against a "
            "plaintext local Postgres, set DATABASE_TLS_REQUIRED=false — the documented "
            "opt-out (app/core/config.py) — never in production."
        )
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
