"""Liveness/readiness endpoints (ADR-0018).

Two distinct probes with distinct contracts:

- ``GET /healthz`` — **liveness**: the process is up and can serve. It checks no
  dependency, never touches the database, and always answers fast so an orchestrator
  restarts a hung process without being fooled by a slow-but-alive DB.
- ``GET /readyz`` — **readiness**: is this instance ready to take traffic *right now*?
  In DB mode it runs a short-timeout ``SELECT 1``; in in-memory mode it reports ready
  with no dependency. A not-ready instance answers **503** so it is pulled from the
  load-balancer rotation without being killed.

Neither endpoint exposes secrets, build/version detail that would aid an attacker, or
any PHI — the bodies are fixed, minimal status dicts (ADR-0018).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

router = APIRouter(tags=["health"])

# The readiness DB probe is bounded so a wedged connection cannot make /readyz hang and
# turn a rotation check into an outage. Kept short: readiness must fail fast.
_READYZ_DB_TIMEOUT_SECONDS = 2.0


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness — process is up. No dependencies, always a fast 200 (ADR-0018)."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, response: Response) -> dict[str, str]:
    """Readiness — ready to serve traffic. 503 (PHI-free body) when not (ADR-0018)."""
    if settings.database_url is None:
        # In-memory mode has no external dependency to check — always ready.
        return {"status": "ready", "mode": "in-memory"}

    engine = getattr(request.app.state, "db_engine", None)
    if engine is None:
        # DB configured but the lifespan never built the engine — not ready to serve.
        response.status_code = 503
        return {"status": "not_ready", "mode": "database"}

    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(
                conn.execute(text("SELECT 1")), timeout=_READYZ_DB_TIMEOUT_SECONDS
            )
    except (SQLAlchemyError, OSError, TimeoutError):
        # Unreachable/slow/erroring database — pull this instance from rotation. The
        # underlying error is deliberately NOT echoed: it can carry host/DSN detail.
        response.status_code = 503
        return {"status": "not_ready", "mode": "database"}

    return {"status": "ready", "mode": "database"}
