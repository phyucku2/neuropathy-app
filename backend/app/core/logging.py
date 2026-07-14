"""Structured, PHI-free request logging (ADR-0018).

One JSON line per request on stdout (Twelve-Factor: logs are an event stream the
platform captures). The line carries exactly the fields an operator needs to trace and
measure traffic — and nothing that could carry PHI or a secret:

- ``method`` — the HTTP verb (safe: a fixed vocabulary).
- ``path`` — the matched **route template** (``/capabilities/{key}``), never the raw
  request path. A raw path can embed a patient id, an email, or an opaque token in a
  path segment; the template cannot.
- ``status`` — the response status code.
- ``duration_ms`` — server-side latency.
- ``request_id`` — from an inbound ``X-Request-ID`` or freshly generated. Resolved BEFORE
  the downstream call and stashed on ``request.state.request_id`` so the error seam
  (app/core/errors.py) reads the SAME id, then echoed back on the response so a
  client/proxy trace correlates to both the log line and any error event.
- ``env`` — ``settings.app_env``.

**Every request is logged, including 500s.** The downstream call is wrapped so an unhandled
exception (which becomes a 500 after the normal error handling renders it) still emits its
one log line — status 500, the resolved request id, method, and route template (or the
``__unmatched__`` sentinel when the exception fired before routing) — then re-raises
unchanged. A 500 is therefore never a logging blind spot, and it shares a request id with
its error event.

Deliberately **never** logged: query strings, request/response bodies, headers
(``Authorization``/cookies/tokens), path parameter *values*, or anything derived from
them. There is no code path that widens this set — the middleware builds the dict from
the whitelist above only.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_LOGGER_NAME = "app.request"

# Logged in place of a route template when no route matched (e.g. a 404). The raw path
# is withheld on purpose — an unmatched path is exactly where a stray id/email would be.
UNMATCHED_ROUTE = "__unmatched__"

_request_logger = logging.getLogger(REQUEST_LOGGER_NAME)


class JsonLogFormatter(logging.Formatter):
    """Render a record as a single-line JSON object.

    The request middleware passes its already-built field dict via ``extra={"fields":
    ...}``; any other log record degrades gracefully to ``{"message": ...}`` so a
    stray library log never crashes the handler.
    """

    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", None)
        payload = dict(fields) if isinstance(fields, dict) else {"message": record.getMessage()}
        payload.setdefault("level", record.levelname)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def configure_logging(*, debug: bool) -> None:
    """Install one JSON stdout handler on the request logger (idempotent).

    Level follows ``app_debug`` (DEBUG when on, INFO otherwise). Idempotent so the app
    factory can call it on every ``create_app`` — tests build many instances — without
    stacking duplicate handlers. ``propagate`` stays on so pytest's caplog captures.
    """
    _request_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    for handler in _request_logger.handlers:
        if getattr(handler, "_neuro_json_handler", False):
            return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    # Marker so a second configure_logging() recognizes its own handler and no-ops.
    handler._neuro_json_handler = True  # type: ignore[attr-defined]
    _request_logger.addHandler(handler)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured, PHI-free JSON log line per request (ADR-0018)."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Resolve the request id up front and stash it on request.state BEFORE calling
        # downstream, so the error seam reads the SAME id even on a 500 that never reaches
        # the success branch below (errors.build_error_event reads request.state.request_id).
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Unhandled exception -> the app renders its normal 500. Emit THIS request's one
            # log line (status 500) so a 500 is never a logging blind spot, then re-raise
            # unchanged; the client-facing error response is untouched.
            self._log(request, status=500, request_id=request_id, started=started)
            raise
        self._log(request, status=response.status_code, request_id=request_id, started=started)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @staticmethod
    def _log(request: Request, *, status: int, request_id: str, started: float) -> None:
        """Emit the one PHI-free JSON line for this request (whitelist fields only)."""
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        # After routing, Starlette parks the matched Route on the (shared) scope. Its `.path`
        # is the template; absent (a hard 500 before routing, or an unmatched path) means
        # withhold the raw path -> the sentinel, never a segment that could carry PHI.
        route = request.scope.get("route")
        path_template = getattr(route, "path", None) or UNMATCHED_ROUTE
        _request_logger.info(
            "http_request",
            extra={
                "fields": {
                    "event": "http_request",
                    "method": request.method,
                    "path": path_template,
                    "status": status,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                    "env": settings.app_env,
                }
            },
        )
