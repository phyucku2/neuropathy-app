"""Prometheus metrics are PHI-free and route-templated (ADR-0021).

These tests are the enforcement seam for the metrics contract: `/metrics` renders
Prometheus text, requests increment the counter, the route label is the *template* (never
a raw path that could carry a patient id), a 5xx is still counted, and the DB pool gauge
reflects the live engine. Any change that leaks a raw path/PHI into a label must break a
test here.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import RequestLoggingMiddleware
from app.core.metrics import (
    CONTENT_TYPE_LATEST,
    METRICS_REGISTRY,
    UNMATCHED_ROUTE,
    MetricsMiddleware,
    record_ai_narrative_event,
    render_metrics,
    route_template,
    update_db_pool_gauge,
)
from app.main import app, create_app

client = TestClient(app)


def test_metrics_endpoint_returns_prometheus_text() -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == CONTENT_TYPE_LATEST
    # Static app metrics are always present, PHI-free.
    assert "app_up 1.0" in resp.text
    assert "http_requests_total" in resp.text


def test_request_increments_the_counter() -> None:
    before = METRICS_REGISTRY.get_sample_value(
        "http_requests_total", {"method": "GET", "route": "/healthz", "status": "200"}
    )
    client.get("/healthz")
    after = METRICS_REGISTRY.get_sample_value(
        "http_requests_total", {"method": "GET", "route": "/healthz", "status": "200"}
    )
    assert (after or 0.0) == (before or 0.0) + 1.0


def test_metric_labels_use_route_template_and_never_the_raw_uuid() -> None:
    """The prompt's core assertion: a request to /clinic/patients/<uuid>/trajectory is
    labelled with the TEMPLATE, and the uuid appears NOWHERE in /metrics output. Routing
    matches the template before the auth dependency runs, so the (401) request is still
    recorded under the template — the raw uuid never enters a label."""
    patient_id = uuid.uuid4()
    # Unauthenticated -> 401, but the route template is on the scope after matching.
    resp = client.get(f"/clinic/patients/{patient_id}/trajectory")
    assert resp.status_code == 401

    metrics_text = client.get("/metrics").text
    assert "/clinic/patients/{patient_id}/trajectory" in metrics_text
    assert str(patient_id) not in metrics_text


def _app_with_metrics() -> FastAPI:
    application = FastAPI()
    application.add_middleware(MetricsMiddleware)

    @application.get("/boom/{token}")
    async def boom(token: str) -> dict[str, str]:
        raise RuntimeError(f"synthetic failure for {token}")

    return application


def test_unhandled_exception_is_counted_as_5xx_and_leaks_no_path() -> None:
    """A 5xx must be counted (feeds the high-5xx alert) with the template label only —
    the raising handler's path segment never reaches a metric."""
    secret_segment = f"leaky-{uuid.uuid4()}"
    bare = TestClient(_app_with_metrics(), raise_server_exceptions=False)

    resp = bare.get(f"/boom/{secret_segment}")
    assert resp.status_code == 500

    count = METRICS_REGISTRY.get_sample_value(
        "http_requests_total", {"method": "GET", "route": "/boom/{token}", "status": "500"}
    )
    assert count == 1.0
    assert secret_segment not in render_metrics().decode()


def test_route_template_falls_back_to_sentinel_for_unmatched() -> None:
    """A request that matched no route records the sentinel, never its raw path."""
    resp = client.get(f"/no-such-route/{uuid.uuid4()}")
    assert resp.status_code == 404
    # The unmatched request is counted under the sentinel template.
    assert (
        METRICS_REGISTRY.get_sample_value(
            "http_requests_total",
            {"method": "GET", "route": UNMATCHED_ROUTE, "status": "404"},
        )
        or 0.0
    ) >= 1.0


class _FakePool:
    def __init__(self, in_use: int) -> None:
        self._in_use = in_use

    def checkedout(self) -> int:
        return self._in_use


class _FakeEngine:
    def __init__(self, in_use: int) -> None:
        self.pool = _FakePool(in_use)


def test_db_pool_gauge_reflects_engine_and_zero_without_one() -> None:
    update_db_pool_gauge(_FakeEngine(in_use=3))
    assert METRICS_REGISTRY.get_sample_value("db_connection_pool_in_use") == 3.0
    update_db_pool_gauge(None)  # in-memory mode: no engine -> 0
    assert METRICS_REGISTRY.get_sample_value("db_connection_pool_in_use") == 0.0


def test_ai_narrative_event_counter_increments_by_type() -> None:
    before = METRICS_REGISTRY.get_sample_value(
        "app_ai_narrative_events_total", {"event": "requested"}
    )
    record_ai_narrative_event("requested")
    after = METRICS_REGISTRY.get_sample_value(
        "app_ai_narrative_events_total", {"event": "requested"}
    )
    assert (after or 0.0) == (before or 0.0) + 1.0


def test_route_template_returns_sentinel_without_a_matched_route() -> None:
    """Unit-level guard on the helper: no route on the scope -> sentinel, not a raw path."""

    class _Req:
        scope: dict[str, object] = {}

    assert route_template(_Req()) == UNMATCHED_ROUTE  # type: ignore[arg-type]


def test_logging_stays_outermost_and_metrics_sits_inside_it() -> None:
    """RequestLoggingMiddleware must remain outermost (ADR-0018); MetricsMiddleware is
    registered just inside it so it counts every request (incl. guard short-circuits)."""
    classes = [m.cls for m in app.user_middleware]
    assert classes[0] is RequestLoggingMiddleware
    assert classes.index(MetricsMiddleware) == 1


def test_fresh_app_also_exposes_metrics_endpoint() -> None:
    """A separately-built app instance carries the same /metrics wiring (no global-only
    registration surprises)."""
    bare = TestClient(create_app())
    assert bare.get("/metrics").status_code == 200
