"""Error-reporting seam — off by default, self-hostable, PHI-scrubbing, fail-safe
(ADR-0021).

Mirrors the Narrator seam (app/ai/narrative.py): a swappable ``ErrorReporter`` PROTOCOL
that stays OFF until an operator configures a self-hosted, permissive collector
(``settings.error_reporting_dsn``). It is wired by ``ErrorReportingMiddleware`` to capture
**unhandled** exceptions (the ones that become a 5xx) and CONTAIN them (readiness plan
§1B C3): the client always receives the same static, PHI-free 500 body, and the exception
never propagates to the ASGI server — so ``str(exc)`` (which can echo request values)
never reaches uvicorn.error or a server-rendered traceback.

**PHI scrub by construction.** The emitted event (``ErrorEvent``) is built from a fixed
whitelist of safe fields only — exception *type* name, route *template*, method, status,
request id, ISO timestamp, env. The exception **message is never included** (it could echo
a patient id/email/value), and neither is the query string, body, headers, or any path
parameter value. There is no code path that widens this set.

**Fail-safe.** A reporter that raises, times out, or is misconfigured must never break the
request: the middleware swallows every reporter error and still renders the same static
500 body.
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
from starlette.responses import JSONResponse, Response

from app.core.logging import REQUEST_ID_HEADER
from app.core.metrics import route_template

_log = logging.getLogger(__name__)

# The status recorded for an unhandled exception: it becomes a 500 once normal error
# handling renders it. We report at the point the exception propagates, before rendering.
_UNHANDLED_STATUS = 500

# The ONE body every unhandled exception renders (readiness plan §1B C3): static and
# PHI-free by construction — there is no code path that puts str(exc), a value, or any
# request datum into it. Kept a module constant so tests assert the exact contract.
INTERNAL_ERROR_DETAIL = "Internal server error"


@dataclass(frozen=True)
class ErrorEvent:
    """A PHI-scrubbed error event — a fixed whitelist of safe fields, nothing else.

    Every field here is either a fixed vocabulary (method, status), software-derived
    identifier (exception type name, route *template*), a correlation id shared with the
    request log line (resolved by the logging middleware onto request.state), or a
    timestamp. NONE is derived from the exception message, request body, query string,
    headers, or any patient datum."""

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


def _resolve_request_id(request: Request) -> str | None:
    """The correlation id shared with the request log line.

    The logging middleware (outermost) resolves an id for EVERY request — the inbound
    ``X-Request-ID`` or a generated one — and stashes it on ``request.state.request_id``
    before the exception is raised, so reading it here makes the error event and the 500 log
    line carry ONE id. Fall back to the inbound header (for a bare deployment without the
    logging middleware), then ``None`` — never invented from PHI."""
    state_id = getattr(request.state, "request_id", None)
    if isinstance(state_id, str):
        return state_id
    return request.headers.get(REQUEST_ID_HEADER)


def build_error_event(request: Request, exc: BaseException, *, env: str) -> ErrorEvent:
    """Construct the scrubbed event from the request + exception TYPE only.

    The exception instance is used ONLY for ``type(exc).__name__`` — never ``str(exc)`` —
    so a message carrying a fake patient id/email can never reach the event."""
    return ErrorEvent(
        exception_type=type(exc).__name__,
        route=route_template(request),
        method=request.method,
        status=_UNHANDLED_STATUS,
        # Shared with the request log line: resolved by the logging middleware onto
        # request.state (see _resolve_request_id); absent → None, never invented from PHI.
        request_id=_resolve_request_id(request),
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
    """Capture unhandled exceptions: ONE scrubbed event, then CONTAINMENT (ADR-0021 +
    readiness plan §1B C3).

    Composed INSIDE the request-logging + metrics middleware and OUTSIDE the router, so it
    is the first thing an unhandled exception reaches. It emits the one scrubbed event
    (only when a reporter is configured; any reporter failure is swallowed) and then
    RETURNS the static PHI-free 500 body instead of re-raising: an exception message can
    echo a patient value, and re-raising would hand exactly that string to uvicorn.error
    and the ASGI server's traceback renderer. Note Starlette's
    ``add_exception_handler(Exception, ...)`` cannot do this — ServerErrorMiddleware sends
    the handler's response and then re-raises anyway — which is why containment lives
    here, in the app's own middleware. Logging/metrics (outside) see an ordinary 500
    response on their normal paths, so 'one log line / one count per request' holds."""

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
            # Containment (§1B C3): the static body, never str(exc) or a rendered
            # traceback. The exception stops HERE — nothing downstream of this
            # middleware ever sees it, so no server layer can print its message.
            return JSONResponse(
                status_code=_UNHANDLED_STATUS, content={"detail": INTERNAL_ERROR_DETAIL}
            )

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
    "INTERNAL_ERROR_DETAIL",
    "ErrorEvent",
    "ErrorReporter",
    "ErrorReportingMiddleware",
    "HttpErrorReporter",
    "build_error_event",
]
