"""Structured request logging is PHI-free and path-templated (ADR-0018).

These tests are the enforcement seam for the logging contract: they assert the exact
field set, that the logged path is the route *template* (never the raw path that could
carry a patient id/email), that request ids round-trip, and that the JSON formatter
renders safely. Any change that widens what is logged must break a test here.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import (
    REQUEST_ID_HEADER,
    REQUEST_LOGGER_NAME,
    UNMATCHED_ROUTE,
    JsonLogFormatter,
    RequestLoggingMiddleware,
    configure_logging,
)

_EXPECTED_FIELDS = {"event", "method", "path", "status", "duration_ms", "request_id", "env"}


def _app_with_logging() -> FastAPI:
    application = FastAPI()
    application.add_middleware(RequestLoggingMiddleware)

    @application.get("/patients/{patient_id}")
    async def read_patient(patient_id: str) -> dict[str, str]:
        return {"seen": patient_id}

    return application


def _only_request_record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    records = [r for r in caplog.records if r.name == REQUEST_LOGGER_NAME]
    assert len(records) == 1
    return records[0]


def test_logs_route_template_and_excludes_phi(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=REQUEST_LOGGER_NAME)
    client = TestClient(_app_with_logging())

    resp = client.get("/patients/synthetic-secret-999?email=nope@example.com")

    assert resp.status_code == 200
    fields = _only_request_record(caplog).fields  # type: ignore[attr-defined]
    assert set(fields) == _EXPECTED_FIELDS
    assert fields["path"] == "/patients/{patient_id}"  # template, not the raw id
    assert fields["method"] == "GET"
    assert fields["status"] == 200
    assert isinstance(fields["duration_ms"], float)

    # The raw id, the query string, and its email are nowhere in the serialized line.
    serialized = json.dumps(fields)
    assert "synthetic-secret-999" not in serialized
    assert "nope@example.com" not in serialized
    assert "email" not in serialized
    # The generated request id is echoed back for client-side correlation.
    assert resp.headers[REQUEST_ID_HEADER] == fields["request_id"]


def test_inbound_request_id_is_reused(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=REQUEST_LOGGER_NAME)
    client = TestClient(_app_with_logging())

    resp = client.get("/patients/1", headers={REQUEST_ID_HEADER: "trace-abc-123"})

    assert resp.headers[REQUEST_ID_HEADER] == "trace-abc-123"
    assert _only_request_record(caplog).fields["request_id"] == "trace-abc-123"  # type: ignore[attr-defined]


def test_unmatched_route_withholds_the_raw_path(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=REQUEST_LOGGER_NAME)
    client = TestClient(_app_with_logging())

    resp = client.get("/unknown/patient-secret-42")

    assert resp.status_code == 404
    fields = _only_request_record(caplog).fields  # type: ignore[attr-defined]
    assert fields["path"] == UNMATCHED_ROUTE
    assert "patient-secret-42" not in json.dumps(fields)


def test_json_formatter_renders_structured_fields() -> None:
    record = logging.LogRecord(REQUEST_LOGGER_NAME, logging.INFO, __file__, 1, "x", None, None)
    record.fields = {"event": "http_request", "status": 200}  # type: ignore[attr-defined]

    out = json.loads(JsonLogFormatter().format(record))

    assert out == {"event": "http_request", "status": 200, "level": "INFO"}


def test_json_formatter_degrades_for_plain_records() -> None:
    record = logging.LogRecord("some.lib", logging.WARNING, __file__, 1, "plain msg", None, None)

    out = json.loads(JsonLogFormatter().format(record))

    assert out == {"message": "plain msg", "level": "WARNING"}


def test_request_logging_middleware_is_registered_outermost() -> None:
    """Starlette wraps the LAST-added middleware outermost, so RequestLoggingMiddleware
    must sit at index 0 of user_middleware — ahead of the inner upload guard. If it were
    added first (inner), an upload-guard short-circuit would bypass logging entirely."""
    from app.main import app

    assert app.user_middleware[0].cls is RequestLoggingMiddleware


def test_upload_guard_short_circuit_is_still_logged_with_request_id(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An over-declared upload trips the inner guard (422) before routing. Because the
    logging middleware is outermost it must STILL emit exactly one JSON line and echo an
    X-Request-ID header — the 'one line per request' contract holds for short-circuits."""
    from app.core.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "biomech_max_pdf_bytes", 64)
    caplog.set_level(logging.INFO, logger=REQUEST_LOGGER_NAME)
    client = TestClient(app)

    # Body far beyond the (shrunk) cap + multipart overhead, so the declared Content-Length
    # trips the guard before the multipart body is parsed.
    over_declared = b"x" * (128 * 1024)
    resp = client.post(
        "/biomech/reports",
        files={"file": ("report.pdf", over_declared, "application/pdf")},
    )

    assert resp.status_code == 422
    assert resp.json()["detail"] == "Upload exceeds the PDF size cap"
    records = [r for r in caplog.records if r.name == REQUEST_LOGGER_NAME]
    assert len(records) == 1
    assert REQUEST_ID_HEADER in resp.headers
    assert records[0].fields["request_id"] == resp.headers[REQUEST_ID_HEADER]  # type: ignore[attr-defined]


def test_configure_logging_is_idempotent_and_sets_level() -> None:
    logger = logging.getLogger(REQUEST_LOGGER_NAME)
    for handler in list(logger.handlers):
        if getattr(handler, "_neuro_json_handler", False):
            logger.removeHandler(handler)
    # A pre-existing, unrelated handler: configure_logging must scan past it (not treat
    # it as its own) before installing the JSON handler.
    unrelated = logging.NullHandler()
    logger.addHandler(unrelated)
    try:
        _run_idempotency_checks(logger)
    finally:
        logger.removeHandler(unrelated)


def _run_idempotency_checks(logger: logging.Logger) -> None:
    configure_logging(debug=False)
    after_first = [h for h in logger.handlers if getattr(h, "_neuro_json_handler", False)]
    assert len(after_first) == 1
    assert logger.level == logging.INFO

    configure_logging(debug=True)  # must NOT stack a second handler
    after_second = [h for h in logger.handlers if getattr(h, "_neuro_json_handler", False)]
    assert len(after_second) == 1
    assert logger.level == logging.DEBUG
