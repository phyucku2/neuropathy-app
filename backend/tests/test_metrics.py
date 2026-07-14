"""Prometheus metrics are PHI-free and route-templated (ADR-0021).

These tests are the enforcement seam for the metrics contract: `/metrics` renders
Prometheus text, requests increment the counter, the route label is the *template* (never
a raw path that could carry a patient id), a 5xx is still counted, and the DB pool gauge
reflects the live engine. Any change that leaks a raw path/PHI into a label must break a
test here.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, Counter, generate_latest, values
from prometheus_client.values import MultiProcessValue

from app.core import metrics as metrics_module
from app.core.logging import RequestLoggingMiddleware
from app.core.metrics import (
    APP_UP,
    CONTENT_TYPE_LATEST,
    DB_POOL_IN_USE,
    METRICS_REGISTRY,
    PROMETHEUS_MULTIPROC_DIR_ENV,
    UNMATCHED_ROUTE,
    MetricsMiddleware,
    build_scrape_registry,
    mark_worker_dead,
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


# --- multiprocess exposition (multi-worker deployment; ADR-0021) ----------------------


def test_pool_and_up_gauges_declare_multiprocess_mode() -> None:
    """Across workers the gauges must aggregate, not report one random worker's value: the
    pool sums live workers, app_up reports a single liveness series that drops dead workers.
    A missing/wrong mode would silently corrupt the multi-worker scrape."""
    assert DB_POOL_IN_USE._multiprocess_mode == "livesum"  # noqa: SLF001
    assert APP_UP._multiprocess_mode == "livemax"  # noqa: SLF001


def test_scrape_registry_is_in_process_when_multiproc_dir_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dev / single process: the scrape renders the in-process registry as before."""
    monkeypatch.delenv(PROMETHEUS_MULTIPROC_DIR_ENV, raising=False)
    assert build_scrape_registry() is METRICS_REGISTRY
    assert b"app_up" in render_metrics()  # the in-process path still renders app metrics


def test_scrape_registry_aggregates_worker_files_in_multiproc_mode(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With PROMETHEUS_MULTIPROC_DIR set, a scrape must build a fresh
    MultiProcessCollector-backed registry that AGGREGATES samples every worker wrote to the
    shared dir — not just the one worker Prometheus reached. We simulate a worker writing a
    counter file, then assert the scrape sums it and renders without error."""
    monkeypatch.setenv(PROMETHEUS_MULTIPROC_DIR_ENV, str(tmp_path))
    # Flip prometheus_client's value backing to multiprocess for the duration of the test so
    # a metric created here writes a real file into the shared dir (as a worker would).
    original_value_class = values.ValueClass
    values.ValueClass = MultiProcessValue()
    try:
        worker_registry = CollectorRegistry()
        probe = Counter("mp_probe_total", "synthetic multiproc probe", registry=worker_registry)
        probe.inc(2)

        registry = build_scrape_registry()
        assert registry is not METRICS_REGISTRY  # a fresh registry, not the in-process one
        collectors = list(registry._collector_to_names)  # noqa: SLF001
        assert any(type(c).__name__ == "MultiProcessCollector" for c in collectors)

        # The scrape reads the worker's file from the dir and renders it, no error.
        text = generate_latest(registry).decode()
        assert "mp_probe_total 2.0" in text
    finally:
        values.ValueClass = original_value_class


def test_mark_worker_dead_delegates_only_in_multiproc_mode(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker-death hook clears a dead worker's files in multiprocess mode (so its
    gauges stop skewing sums) and is a safe no-op otherwise."""
    called: list[int] = []
    monkeypatch.setattr(
        metrics_module.multiprocess, "mark_process_dead", lambda pid: called.append(pid)
    )

    monkeypatch.delenv(PROMETHEUS_MULTIPROC_DIR_ENV, raising=False)
    mark_worker_dead(1234)
    assert called == []  # unset dir -> nothing to clean up, never delegates

    monkeypatch.setenv(PROMETHEUS_MULTIPROC_DIR_ENV, str(tmp_path))
    mark_worker_dead(4321)
    assert called == [4321]  # multiprocess mode -> delegates with the dead worker's pid
