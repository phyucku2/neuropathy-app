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

``GET /metrics`` lives here too (ADR-0021): it renders Prometheus-format metrics for a
scraper. It is unauthenticated like ``/healthz``/``/readyz`` and, by the same posture,
exposes **nothing sensitive** — every metric is PHI-free by construction (route templates,
not raw paths; aggregate counters, never a subject). In a K8s deployment it is scraped on
the internal network; keeping it PHI-free means exposure is not a PHI risk regardless of
where it is bound (ADR-0021 §1).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.metrics import CONTENT_TYPE_LATEST, render_metrics, update_db_pool_gauge

router = APIRouter(tags=["health"])

# The readiness DB probe is bounded so a wedged connection cannot make /readyz hang and
# turn a rotation check into an outage. This bounds the WHOLE probe — the TCP connect +
# Postgres handshake AND the SELECT 1 — not just the query: a network-partitioned DB
# stalls at handshake, which used to fall outside the timeout. Kept short: readiness must
# fail fast (the engine also caps connection establishment — see app/db/session.py).
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
        # Bound connect + handshake + query together: on a network partition the
        # `engine.connect()` handshake is exactly what stalls, so the timeout must wrap
        # the whole block, not the SELECT alone.
        async with asyncio.timeout(_READYZ_DB_TIMEOUT_SECONDS):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError):
        # Unreachable/slow/erroring database — pull this instance from rotation. The
        # underlying error is deliberately NOT echoed: it can carry host/DSN detail.
        response.status_code = 503
        return {"status": "not_ready", "mode": "database"}

    return {"status": "ready", "mode": "database"}


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    """Prometheus metrics — PHI-free by construction (ADR-0021).

    Refreshes the DB pool gauge from the live engine at scrape time (an integer off the
    in-process pool; 0 in in-memory mode), then renders the registry as Prometheus text.
    Unauthenticated like the health probes; exposes no secret, no version detail, no PHI —
    labels are route *templates* and fixed vocabularies only, never raw paths or subjects.
    """
    update_db_pool_gauge(getattr(request.app.state, "db_engine", None))
    return Response(content=render_metrics(), media_type=CONTENT_TYPE_LATEST)
