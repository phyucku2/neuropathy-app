"""App serving-startup config guard (sweep #5) — the JWT signing-secret check that runs in
the lifespan, NOT at Settings construction, so migrations/tooling are unaffected.

All synthetic values; the database URL never has to be reachable because the guard runs
before the engine connects (and /healthz is liveness-only, no DB).
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app

_SYNTHETIC_DB_URL = "postgresql+asyncpg://synthetic/db"
_A_JWT_SECRET = "synthetic-configured-secret-not-a-real-one"


def test_multi_worker_db_mode_without_jwt_secret_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DATABASE_URL set + WEB_CONCURRENCY > 1 + no JWT_SECRET must fail the worker boot fast
    and loud — the per-worker ephemeral-key 401 storm the finding is about."""
    monkeypatch.setattr(settings, "database_url", _SYNTHETIC_DB_URL)
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with pytest.raises(RuntimeError, match="JWT_SECRET"), TestClient(create_app()):
        pass


def test_single_worker_db_mode_without_jwt_secret_boots_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """One worker can still run on the per-process ephemeral key, so DB mode without a
    JWT_SECRET only WARNS (mirroring secret_store_key) — it does not block boot."""
    monkeypatch.setattr(settings, "database_url", _SYNTHETIC_DB_URL)
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)  # unset -> single process
    with (
        caplog.at_level(logging.WARNING, logger="app.main"),
        TestClient(create_app()) as booted,
    ):
        assert booted.get("/healthz").status_code == 200  # came up on the ephemeral key
    assert any("JWT_SECRET is not set" in r.message for r in caplog.records)


def test_multi_worker_db_mode_with_a_jwt_secret_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard fires ONLY on a missing secret: a configured JWT_SECRET boots cleanly even
    at WEB_CONCURRENCY > 1."""
    monkeypatch.setattr(settings, "database_url", _SYNTHETIC_DB_URL)
    monkeypatch.setattr(settings, "jwt_secret", _A_JWT_SECRET)
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with TestClient(create_app()) as booted:
        assert booted.get("/healthz").status_code == 200


def test_in_memory_mode_never_requires_a_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """No DATABASE_URL: the guard is a no-op even at WEB_CONCURRENCY > 1 (nothing durable to
    protect); the ephemeral-key path stays for unit tests / DB-less dev."""
    monkeypatch.setattr(settings, "database_url", None)
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setenv("WEB_CONCURRENCY", "3")
    with TestClient(create_app()) as booted:
        assert booted.get("/healthz").status_code == 200
