"""Error-reporting seam — off by default, self-hostable, PHI-scrubbing, fail-safe
(ADR-0021).

Mirrors the Narrator seam (app/ai/narrative.py): a swappable ``ErrorReporter`` PROTOCOL
that stays OFF until an operator configures a self-hosted, permissive collector
(``settings.error_reporting_dsn``). It is wired by ``ErrorReportingMiddleware`` to capture
**unhandled** exceptions (the ones that become a 5xx) WITHOUT changing the client-facing
response and WITHOUT logging PHI.

**PHI scrub by construction.** The emitted event (``ErrorEvent``) is built from a fixed
whitelist of safe fields only — exception *type* name, route *template*, method, status,
request id, ISO timestamp, env. The exception **message is never included** (it could echo
a patient id/email/value), and neither is the query string, body, headers, or any path
parameter value. There is no code path that widens this set.

**Fail-safe.** A reporter that raises, times out, or is misconfigured must never break the
request: the middleware swallows every reporter error and lets the original response (the
app's normal 500) proceed unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import REQUEST_ID_HEADER
from app.core.metrics import route_template

_log = logging.getLogger(__name__)

# The status recorded for an unhandled exception: it becomes a 500 once normal error
# handling renders it. We report at the point the exception propagates, before rendering.
_UNHANDLED_STATUS = 500


@dataclass(frozen=True)
class ErrorEvent:
    """A PHI-scrubbed error event — a fixed whitelist of safe fields, nothing else.

    Every field here is either a fixed vocabulary (method, status), software-derived
    identifier (exception type name, route *template*), a correlation id echoed from the
    request header, or a timestamp. NONE is derived from the exception message, request
    body, query string, headers, or any patient datum."""

    exception_type: str
    route: str
    method: str
    status: int
    request_id: str | None
    timestamp: str
    env: str


class ErrorReporter(Protocol):
    """Forwards a scrubbed ``ErrorEvent`` to a collector, or does nothing (off)."""

    async def report(self, event: ErrorEvent) -> None: ...


def build_error_event(request: Request, exc: BaseException, *, env: str) -> ErrorEvent:
    """Construct the scrubbed event from the request + exception TYPE only.

    The exception instance is used ONLY for ``type(exc).__name__`` — never ``str(exc)`` —
    so a message carrying a fake patient id/email can never reach the event."""
    return ErrorEvent(
        exception_type=type(exc).__name__,
        route=route_template(request),
        method=request.method,
        status=_UNHANDLED_STATUS,
        # Correlation id echoed from the inbound header (the same value the logging layer
        # echoes when the client supplies one); absent → None, never invented from PHI.
        request_id=request.headers.get(REQUEST_ID_HEADER),
        timestamp=datetime.now(UTC).isoformat(),
        env=env,
    )


class HttpErrorReporter:
    """Dependency-light reporter: POSTs the scrubbed event as JSON to a self-hosted,
    permissive collector over the existing httpx client (no new dependency, no SaaS SDK,
    no surprise egress beyond the configured URL — ADR-0021).

    Fire-and-forget with a short timeout; ``report`` never raises (the middleware also
    guards, but keeping the transport itself total means a stray client is still safe)."""

    def __init__(
        self, dsn: str, *, timeout: float, client: httpx.AsyncClient | None = None
    ) -> None:
        self._dsn = dsn
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def report(self, event: ErrorEvent) -> None:
        try:
            response = await self._client.post(self._dsn, json=asdict(event))
            response.raise_for_status()
        except Exception:  # noqa: BLE001 — reporting is best-effort; never surface to caller
            _log.warning("error report POST failed (swallowed)", exc_info=False)

    async def aclose(self) -> None:
        await self._client.aclose()


class ErrorReportingMiddleware(BaseHTTPMiddleware):
    """Capture unhandled exceptions and forward a scrubbed event — fail-safe (ADR-0021).

    Composed INSIDE the request-logging + metrics middleware and OUTSIDE the router, so it
    sees the exception on its way to the normal 500 handler. It re-raises unchanged, so the
    client still gets the app's normal error response; only a scrubbed event is emitted, and
    only when a reporter is configured. Any reporter failure is swallowed."""

    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        *,
        reporter_factory: Callable[[], ErrorReporter | None],
        env: str,
    ) -> None:
        super().__init__(app)
        self._reporter_factory = reporter_factory
        self._env = env

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            await self._safe_report(request, exc)
            raise  # unchanged propagation → normal error handling renders the 500

    async def _safe_report(self, request: Request, exc: BaseException) -> None:
        """Report the exception if a reporter is configured; never let this break the
        request (a reporter/build failure is logged PHI-free and swallowed)."""
        reporter = self._reporter_factory()
        if reporter is None:
            return  # off by default: no reporter configured → no-op
        try:
            await reporter.report(build_error_event(request, exc, env=self._env))
        except Exception:  # noqa: BLE001 — fail-safe: a reporter error must not break the request
            _log.warning("error reporter raised (swallowed)", exc_info=False)


__all__ = [
    "ErrorEvent",
    "ErrorReporter",
    "ErrorReportingMiddleware",
    "HttpErrorReporter",
    "build_error_event",
]
