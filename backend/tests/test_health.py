"""Liveness/readiness surface (ADR-0018) — deterministic, no network, no PHI.

The DB-mode readiness paths that DON'T need a live database (engine missing; database
unreachable) are exercised here with synthetic/unreachable URLs so the branch coverage
holds without Postgres. The happy DB path is pinned by the Postgres integration suite
(tests/integration/test_readiness.py).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app, create_app

client = TestClient(app)


def test_healthz_ok() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_reports_service() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "neuropathy-app backend"


def test_readyz_in_memory_mode_is_ready() -> None:
    """No DATABASE_URL: no dependency to check, so readiness is immediate."""
    assert settings.database_url is None  # the default test posture
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "mode": "in-memory"}


def test_readyz_db_configured_but_engine_unbuilt_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB mode with no engine on app.state (lifespan never ran) -> 503, no leak."""
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://synthetic/db")
    # A plain TestClient (no context manager) does NOT run the lifespan, so
    # app.state.db_engine is never set — exactly the "configured but unbuilt" case.
    bare = TestClient(create_app())
    resp = bare.get("/readyz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready", "mode": "database"}


def test_readyz_unreachable_database_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """DB mode with a real engine but an unreachable server -> 503; the underlying
    connection error is never echoed into the body."""
    # Port 1 is unreachable; the engine builds lazily so the failure surfaces only when
    # /readyz runs its SELECT 1.
    monkeypatch.setattr(
        settings, "database_url", "postgresql+asyncpg://postgres:x@127.0.0.1:1/nodb"
    )
    with TestClient(create_app()) as booted:
        resp = booted.get("/readyz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready", "mode": "database"}
