"""The error-reporting seam is off-by-default, PHI-scrubbing, and fail-safe (ADR-0021).

Enforcement seam for the error-reporter contract: OFF with no DSN (no reporter -> no-op);
when configured, exactly one scrubbed event per unhandled exception carrying NONE of the
exception message / patient data; a reporter failure is swallowed (never breaks the
request); and the client-facing response is unchanged. Any regression that leaks PHI into
an event, double-reports, or lets a reporter error escape must break a test here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import _default_error_reporter, get_error_reporter
from app.core.config import settings
from app.core.errors import (
    ErrorEvent,
    ErrorReportingMiddleware,
    HttpErrorReporter,
)
from app.core.logging import (
    REQUEST_ID_HEADER,
    REQUEST_LOGGER_NAME,
    RequestLoggingMiddleware,
)

# A synthetic patient id + email planted INSIDE an exception message; the scrub must keep
# both out of every emitted event.
LEAK_PATIENT_ID = "synthetic-patient-9f3c2a"
LEAK_EMAIL = "leak@example.com"


class _RecordingReporter:
    """Captures the events it is handed (a stand-in for a self-hosted collector)."""

    def __init__(self) -> None:
        self.events: list[ErrorEvent] = []

    async def report(self, event: ErrorEvent) -> None:
        self.events.append(event)


class _RaisingReporter:
    async def report(self, event: ErrorEvent) -> None:
        raise RuntimeError("collector unreachable")


def _app_with_error_reporting(factory: object, *, env: str = "test-env") -> FastAPI:
    application = FastAPI()
    application.add_middleware(
        ErrorReportingMiddleware,
        reporter_factory=factory,
        env=env,
    )

    @application.get("/kaboom/{patient_id}")
    async def kaboom(patient_id: str) -> dict[str, str]:
        # Message deliberately embeds PHI-shaped strings to prove the scrub.
        raise ValueError(f"boom for {patient_id} contact {LEAK_EMAIL}")

    @application.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    return application


def test_off_by_default_no_reporter_is_a_noop() -> None:
    """No configured reporter (factory -> None): an unhandled error still 500s normally,
    and nothing is emitted."""
    client = TestClient(_app_with_error_reporting(lambda: None), raise_server_exceptions=False)
    resp = client.get(f"/kaboom/{LEAK_PATIENT_ID}")
    assert resp.status_code == 500  # normal error response, unchanged


def test_happy_path_does_not_report() -> None:
    reporter = _RecordingReporter()
    client = TestClient(_app_with_error_reporting(lambda: reporter))
    assert client.get("/ok").status_code == 200
    assert reporter.events == []  # only unhandled exceptions are reported


def test_unhandled_error_emits_exactly_one_scrubbed_event_without_phi() -> None:
    reporter = _RecordingReporter()
    client = TestClient(_app_with_error_reporting(lambda: reporter), raise_server_exceptions=False)

    resp = client.get(f"/kaboom/{LEAK_PATIENT_ID}", headers={REQUEST_ID_HEADER: "trace-xyz"})
    assert resp.status_code == 500  # client-facing response is unchanged

    assert len(reporter.events) == 1  # exactly one report
    event = reporter.events[0]
    assert event.exception_type == "ValueError"
    assert event.route == "/kaboom/{patient_id}"  # template, not the raw path
    assert event.method == "GET"
    assert event.status == 500
    assert event.request_id == "trace-xyz"  # correlation id echoed from the header
    assert event.env == "test-env"

    # The scrub: neither the exception message's fake patient id/email nor the raw path
    # segment appears anywhere in the serialized event.
    serialized = json.dumps(asdict(event))
    assert LEAK_PATIENT_ID not in serialized
    assert LEAK_EMAIL not in serialized
    assert "boom for" not in serialized  # the exception message body never leaks


def test_request_id_is_none_when_no_header_supplied() -> None:
    reporter = _RecordingReporter()
    client = TestClient(_app_with_error_reporting(lambda: reporter), raise_server_exceptions=False)
    client.get(f"/kaboom/{LEAK_PATIENT_ID}")
    assert reporter.events[0].request_id is None  # never invented from PHI


def test_reporter_failure_is_swallowed() -> None:
    """A reporter that raises must never break the request (fail-safe)."""
    client = TestClient(
        _app_with_error_reporting(lambda: _RaisingReporter()), raise_server_exceptions=False
    )
    resp = client.get(f"/kaboom/{LEAK_PATIENT_ID}")
    assert resp.status_code == 500  # request still completes with the normal error


# --- correlation: the 500 log line and the error event share one request id -----------


def _correlated_app(reporter: object) -> FastAPI:
    """The production onion for the seam: RequestLoggingMiddleware OUTERMOST (resolves the
    request id onto request.state, logs every request incl. 500s) wrapping
    ErrorReportingMiddleware (reads that id for the scrubbed event). Last-added is outermost
    in Starlette, so logging is added last."""
    application = FastAPI()
    application.add_middleware(ErrorReportingMiddleware, reporter_factory=reporter, env="test-env")
    application.add_middleware(RequestLoggingMiddleware)

    @application.get("/kaboom/{patient_id}")
    async def kaboom(patient_id: str) -> dict[str, str]:
        raise ValueError(f"boom for {patient_id} contact {LEAK_EMAIL}")

    return application


def _only_request_field(caplog: pytest.LogCaptureFixture) -> dict[str, object]:
    records = [r for r in caplog.records if r.name == REQUEST_LOGGER_NAME]
    assert len(records) == 1  # exactly one request-log line, even for a 500
    return dict(records[0].fields)  # type: ignore[attr-defined]


def test_500_log_line_and_error_event_share_a_generated_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 500 with NO inbound X-Request-ID produces one request-log line carrying a GENERATED
    id AND an error event carrying the SAME id — correlation works without a client header.
    Both are PHI-free."""
    caplog.set_level(logging.INFO, logger=REQUEST_LOGGER_NAME)
    reporter = _RecordingReporter()
    client = TestClient(_correlated_app(lambda: reporter), raise_server_exceptions=False)

    resp = client.get(f"/kaboom/{LEAK_PATIENT_ID}")
    assert resp.status_code == 500  # client-facing response unchanged

    fields = _only_request_field(caplog)
    assert fields["status"] == 500
    assert fields["path"] == "/kaboom/{patient_id}"  # template, not the raw id
    logged_id = fields["request_id"]
    assert isinstance(logged_id, str) and len(logged_id) == 32  # generated uuid4 hex

    assert len(reporter.events) == 1
    assert reporter.events[0].request_id == logged_id  # SAME id -> event correlates to log

    # PHI-free on both sides: the planted id/email/message body appear nowhere.
    serialized = json.dumps(fields) + json.dumps(asdict(reporter.events[0]))
    assert LEAK_PATIENT_ID not in serialized
    assert LEAK_EMAIL not in serialized
    assert "boom for" not in serialized


def test_inbound_request_id_is_honored_end_to_end(caplog: pytest.LogCaptureFixture) -> None:
    """An inbound X-Request-ID flows to BOTH the log line and the error event unchanged."""
    caplog.set_level(logging.INFO, logger=REQUEST_LOGGER_NAME)
    reporter = _RecordingReporter()
    client = TestClient(_correlated_app(lambda: reporter), raise_server_exceptions=False)

    client.get(f"/kaboom/{LEAK_PATIENT_ID}", headers={REQUEST_ID_HEADER: "trace-corr-1"})

    assert _only_request_field(caplog)["request_id"] == "trace-corr-1"
    assert reporter.events[0].request_id == "trace-corr-1"


# --- HttpErrorReporter transport ------------------------------------------------------

_EVENT = ErrorEvent(
    exception_type="ValueError",
    route="/kaboom/{patient_id}",
    method="GET",
    status=500,
    request_id="trace-xyz",
    timestamp="2026-07-14T00:00:00+00:00",
    env="test-env",
)


def _http_reporter(handler: httpx.MockTransport) -> HttpErrorReporter:
    return HttpErrorReporter(
        "https://collector.internal/intake",
        timeout=1.0,
        client=httpx.AsyncClient(transport=handler),
    )


async def test_http_reporter_posts_the_scrubbed_event_as_json() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200)

    reporter = _http_reporter(httpx.MockTransport(handler))
    await reporter.report(_EVENT)
    await reporter.aclose()

    assert captured["url"] == "https://collector.internal/intake"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["exception_type"] == "ValueError"
    assert body["route"] == "/kaboom/{patient_id}"
    # The body is exactly the whitelisted fields — nothing else can be present.
    assert set(body) == set(asdict(_EVENT))


async def test_http_reporter_swallows_a_failing_collector() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)  # collector error -> raise_for_status -> swallowed

    reporter = _http_reporter(httpx.MockTransport(handler))
    await reporter.report(_EVENT)  # must NOT raise
    await reporter.aclose()


async def test_http_reporter_swallows_a_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("collector down")

    reporter = _http_reporter(httpx.MockTransport(handler))
    await reporter.report(_EVENT)  # must NOT raise
    await reporter.aclose()


def test_http_reporter_builds_its_own_client_when_none_given() -> None:
    """The default-client branch constructs a real pooled httpx client."""
    reporter = HttpErrorReporter("https://collector.internal/intake", timeout=1.0)
    assert isinstance(reporter._client, httpx.AsyncClient)  # noqa: SLF001


# --- the deps seam (mirrors get_narrator) ---------------------------------------------


async def test_get_error_reporter_is_off_by_default() -> None:
    _default_error_reporter.cache_clear()
    settings_dsn = settings.error_reporting_dsn
    settings.error_reporting_dsn = None
    try:
        assert get_error_reporter() is None
    finally:
        settings.error_reporting_dsn = settings_dsn
        _default_error_reporter.cache_clear()


async def test_get_error_reporter_activates_when_a_dsn_is_configured() -> None:
    _default_error_reporter.cache_clear()
    settings_dsn = settings.error_reporting_dsn
    settings.error_reporting_dsn = "https://collector.internal/intake"
    try:
        reporter = get_error_reporter()
        assert isinstance(reporter, HttpErrorReporter)
        await reporter.aclose()
    finally:
        settings.error_reporting_dsn = settings_dsn
        _default_error_reporter.cache_clear()
