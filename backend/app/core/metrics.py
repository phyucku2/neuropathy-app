"""Prometheus metrics — PHI-free by construction (ADR-0021).

`GET /metrics` (app/api/routes/health.py) renders these in Prometheus text format for a
scraper. Everything here follows one rule: **no label or metric name may carry PHI** — no
raw path, patient id, email, observation value, or free text derived from any of those.

The two dimensions that could carry PHI are handled explicitly:

- **route** is the matched route *template* (``/clinic/patients/{patient_id}/trajectory``),
  read from ``request.scope["route"]`` exactly like the request-logging middleware — never
  the raw path, which can embed a patient id, an email, or a token in a segment. An
  unmatched request records ``__unmatched__`` (the same sentinel the log line uses).
- **status** / **method** are fixed vocabularies (HTTP codes and verbs), safe to label.

App metrics carry only aggregate, subject-free facts: process/platform collectors, an
``app_up`` gauge, the DB pool in-use count, and typed event counters (``event`` label is a
fixed vocabulary such as ``requested`` — never a subject). No counter is ever keyed by who
the request was about.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Recorded for a request that never matched a route (e.g. a 404, or an upload-guard
# short-circuit before routing). Mirrors app/core/logging.UNMATCHED_ROUTE: the raw path is
# withheld on purpose — an unmatched path is exactly where a stray id/email would sit.
UNMATCHED_ROUTE = "__unmatched__"

# A dedicated registry (not the global default) keeps app metrics isolated and lets tests
# read a deterministic set. Process + platform collectors add PHI-free runtime facts
# (``process_*`` cpu/memory/open-fds/start-time, ``python_info``) an operator wants for
# capacity/liveness dashboards.
METRICS_REGISTRY = CollectorRegistry()
ProcessCollector(registry=METRICS_REGISTRY)
PlatformCollector(registry=METRICS_REGISTRY)

# Latency buckets tuned to the app's budgets (read p95 < 200ms, write p95 < 500ms —
# CLAUDE.md §7): dense below 500ms so the SLO boundary is measurable, a tail to catch
# regressions.
_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.5, 5.0)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests, labelled by method, matched route template, and status.",
    ("method", "route", "status"),
    registry=METRICS_REGISTRY,
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds, labelled by method, route template, and status.",
    ("method", "route", "status"),
    buckets=_LATENCY_BUCKETS,
    registry=METRICS_REGISTRY,
)
APP_UP = Gauge(
    "app_up",
    "Static 1 while the process serves; presence/absence signals process liveness.",
    registry=METRICS_REGISTRY,
)
APP_UP.set(1)
DB_POOL_IN_USE = Gauge(
    "db_connection_pool_in_use",
    "Connections currently checked out of the SQLAlchemy pool (0 in in-memory mode).",
    registry=METRICS_REGISTRY,
)
# Typed, subject-free event counter. `event` is a fixed vocabulary (e.g. an ai_narrative
# disclosure being 'requested') — NEVER a patient id, so the alert 'elevated disclosures'
# is derivable without any subject ever entering a label.
AI_NARRATIVE_EVENTS = Counter(
    "app_ai_narrative_events_total",
    "AI narrative lifecycle events by type (subject-free); e.g. a disclosure requested.",
    ("event",),
    registry=METRICS_REGISTRY,
)


class _PoolEngine(Protocol):
    """The slice of an ``AsyncEngine`` the pool gauge needs — its connection pool."""

    @property
    def pool(self) -> _Pool: ...


class _Pool(Protocol):
    def checkedout(self) -> int: ...


def route_template(request: Request) -> str:
    """The matched route template, or the withheld-path sentinel — never the raw path."""
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) else UNMATCHED_ROUTE


def record_request(method: str, route: str, status: int, duration_seconds: float) -> None:
    """Record one request into the counter + latency histogram (PHI-free labels only)."""
    labels = {"method": method, "route": route, "status": str(status)}
    HTTP_REQUESTS.labels(**labels).inc()
    HTTP_REQUEST_DURATION.labels(**labels).observe(duration_seconds)


def record_ai_narrative_event(event: str) -> None:
    """Count a subject-free AI-narrative lifecycle event (e.g. ``requested``)."""
    AI_NARRATIVE_EVENTS.labels(event=event).inc()


def update_db_pool_gauge(engine: _PoolEngine | None) -> None:
    """Refresh the pool gauge from the live engine, or 0 when there is no DB engine.

    Read at scrape time (cheap: an integer off the in-process pool), so the gauge never
    needs a background sampler. In-memory mode has no engine → 0."""
    DB_POOL_IN_USE.set(engine.pool.checkedout() if engine is not None else 0)


def render_metrics() -> bytes:
    """Serialize the registry to Prometheus text (used by the /metrics endpoint)."""
    return generate_latest(METRICS_REGISTRY)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record every request's count + latency with PHI-free labels (ADR-0021).

    Composed INSIDE the request-logging middleware (which must stay outermost — ADR-0018)
    and OUTSIDE the upload guard, so it observes guard short-circuits too. It records in a
    ``finally`` so an unhandled exception (a 5xx) is still counted — that is what makes the
    'high 5xx rate' alert measurable — before the exception propagates to the normal
    error handling (the client-facing response is never changed here)."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        status = 500  # default stands if call_next raises before a response exists
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration = time.perf_counter() - started
            record_request(request.method, route_template(request), status, duration)


__all__ = [
    "CONTENT_TYPE_LATEST",
    "MetricsMiddleware",
    "record_ai_narrative_event",
    "render_metrics",
    "update_db_pool_gauge",
]
