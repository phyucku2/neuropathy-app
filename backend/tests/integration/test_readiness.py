"""Readiness against a live Postgres (ADR-0018): with DATABASE_URL pointed at the
migrated test database and the lifespan run, /readyz runs its SELECT 1 and reports
ready. The unreachable-database (503) path is covered without Postgres in
tests/test_health.py; this pins the happy path against the real server.

Needs TEST_DATABASE_URL (the CI Postgres service provides it) and skips cleanly
otherwise. All synthetic — no patient data (CLAUDE.md §5).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app

requires_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Readiness DB test needs TEST_DATABASE_URL (the CI service provides it)",
)


@requires_postgres
def test_readyz_reports_ready_against_a_live_database(
    migrated_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", migrated_database)
    # The context manager runs the lifespan, which builds the engine on app.state.
    with TestClient(create_app()) as booted:
        resp = booted.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "mode": "database"}


@requires_postgres
def test_healthz_is_liveness_only_and_ignores_the_database(
    migrated_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Liveness never touches the DB: it answers 200 regardless of DB state."""
    monkeypatch.setattr(settings, "database_url", migrated_database)
    with TestClient(create_app()) as booted:
        resp = booted.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
