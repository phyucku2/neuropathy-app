"""Smoke tests for the app surface — deterministic, no network, no PHI."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_ok() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_reports_service() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "neuropathy-app backend"
