"""App serving-startup guard tests (sweep #5; readiness plan §1B C1/C2/C4) — the
JWT_SECRET / SECRET_STORE_KEY / APP_DEBUG checks that run in the lifespan, NOT at
Settings construction, so migrations/tooling are unaffected.

All synthetic values; the database URL never has to be reachable because the guards run
before the engine connects, the engine itself is lazy (nothing connects until the first
request), and /healthz is liveness-only, no DB. The boot-success URL carries
``?ssl=require`` because the multi-worker serving path ALSO enforces Postgres TLS
lexically at engine creation (§1B C2) — covered explicitly at the bottom.
"""

from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app

_SYNTHETIC_DB_URL = "postgresql+asyncpg://synthetic/db"
# The serving engine refuses a TLS-less Postgres URL in multi-worker mode (§1B C2), so
# boot-success tests use a URL that declares TLS.
_SYNTHETIC_TLS_DB_URL = "postgresql+asyncpg://synthetic/db?ssl=require"
_A_JWT_SECRET = "synthetic-configured-secret-not-a-real-one"
_A_SECRET_STORE_KEY = Fernet.generate_key().decode()


def _serving_config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    database_url: str | None = _SYNTHETIC_TLS_DB_URL,
    jwt_secret: str | None = _A_JWT_SECRET,
    secret_store_key: str | None = _A_SECRET_STORE_KEY,
    app_debug: bool = False,
    workers: str | None = "2",
) -> None:
    """A fully-configured serving posture, minus whatever a test punches out."""
    monkeypatch.setattr(settings, "database_url", database_url)
    monkeypatch.setattr(settings, "jwt_secret", jwt_secret)
    monkeypatch.setattr(settings, "secret_store_key", secret_store_key)
    monkeypatch.setattr(settings, "app_debug", app_debug)
    if workers is None:
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)  # unset -> single process
    else:
        monkeypatch.setenv("WEB_CONCURRENCY", workers)


# ---------------------------------------------------------------- JWT_SECRET (C1-adjacent)


def test_multi_worker_db_mode_without_jwt_secret_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DATABASE_URL set + WEB_CONCURRENCY > 1 + no JWT_SECRET must fail the worker boot fast
    and loud — the per-worker ephemeral-key 401 storm the finding is about."""
    _serving_config(monkeypatch, jwt_secret=None)
    with pytest.raises(RuntimeError, match="JWT_SECRET"), TestClient(create_app()):
        pass


def test_single_worker_db_mode_without_jwt_secret_boots_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """One worker can still run on the per-process ephemeral key, so DB mode without a
    JWT_SECRET only WARNS — it does not block boot."""
    _serving_config(monkeypatch, database_url=_SYNTHETIC_DB_URL, jwt_secret=None, workers=None)
    with (
        caplog.at_level(logging.WARNING, logger="app.main"),
        TestClient(create_app()) as booted,
    ):
        assert booted.get("/healthz").status_code == 200  # came up on the ephemeral key
    assert any("JWT_SECRET is not set" in r.message for r in caplog.records)


# ---------------------------------------------------------------- SECRET_STORE_KEY (C1)


def test_multi_worker_db_mode_without_secret_store_key_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§1B C1: multi-worker DB mode without SECRET_STORE_KEY means every vaulted secret
    (EMR OAuth tokens, MFA TOTP secrets) lands in a per-process in-memory vault —
    invisible to sibling workers, gone on restart. Fail closed, fast and loud."""
    _serving_config(monkeypatch, secret_store_key=None)
    with pytest.raises(RuntimeError, match="SECRET_STORE_KEY"), TestClient(create_app()):
        pass


def test_single_worker_db_mode_without_secret_store_key_boots_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A single-process DB deployment may run on the in-memory vault (fail closed —
    never plaintext to the DB), so the posture is stated as ONE boot-time warning."""
    _serving_config(
        monkeypatch, database_url=_SYNTHETIC_DB_URL, secret_store_key=None, workers=None
    )
    with (
        caplog.at_level(logging.WARNING, logger="app.main"),
        TestClient(create_app()) as booted,
    ):
        assert booted.get("/healthz").status_code == 200
    assert any("SECRET_STORE_KEY is not configured" in r.message for r in caplog.records)


def test_multi_worker_db_mode_with_both_secrets_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guards fire ONLY on missing secrets: a configured JWT_SECRET plus
    SECRET_STORE_KEY boots cleanly even at WEB_CONCURRENCY > 1 (TLS-declaring URL)."""
    _serving_config(monkeypatch, workers="4")
    with TestClient(create_app()) as booted:
        assert booted.get("/healthz").status_code == 200


def test_in_memory_mode_never_requires_serving_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """No DATABASE_URL: every guard is a no-op even at WEB_CONCURRENCY > 1 (nothing
    durable to protect); the ephemeral-key path stays for unit tests / DB-less dev."""
    _serving_config(
        monkeypatch, database_url=None, jwt_secret=None, secret_store_key=None, workers="3"
    )
    with TestClient(create_app()) as booted:
        assert booted.get("/healthz").status_code == 200


# ---------------------------------------------------------------- APP_DEBUG (C4)


def test_multi_worker_db_mode_with_debug_on_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§1B C4: APP_DEBUG in a real (DB + multi-worker) deployment renders per-frame
    locals — raw PHI — into error pages and echoes SQL parameters. Refuse to serve."""
    _serving_config(monkeypatch, app_debug=True)
    with pytest.raises(RuntimeError, match="APP_DEBUG"), TestClient(create_app()):
        pass


def test_single_worker_db_mode_with_debug_on_boots_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Dev against a local database is legitimate: single-process DB mode with debug
    on WARNS and boots — the guard scopes the hard fail to the real hazard."""
    _serving_config(monkeypatch, database_url=_SYNTHETIC_DB_URL, app_debug=True, workers=None)
    with (
        caplog.at_level(logging.WARNING, logger="app.main"),
        TestClient(create_app()) as booted,
    ):
        assert booted.get("/healthz").status_code == 200
    assert any("APP_DEBUG is on in DB mode" in r.message for r in caplog.records)


def test_in_memory_mode_with_debug_on_is_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """No DATABASE_URL: the debug guard never fires (the in-memory test/dev mode)."""
    _serving_config(monkeypatch, database_url=None, app_debug=True, workers="2")
    with TestClient(create_app()) as booted:
        assert booted.get("/healthz").status_code == 200


# ---------------------------------------------------------------- Postgres TLS (C2)


def test_multi_worker_db_mode_refuses_a_tls_less_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§1B C2: with both secrets configured, a multi-worker boot still refuses a
    DATABASE_URL that carries no TLS-on ssl/sslmode directive — enforced lexically at
    engine creation, before anything ever connects."""
    _serving_config(monkeypatch, database_url=_SYNTHETIC_DB_URL)
    with pytest.raises(RuntimeError, match="TLS"), TestClient(create_app()):
        pass


def test_documented_tls_opt_out_boots_on_a_plaintext_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DATABASE_TLS_REQUIRED=false is the documented local-dev opt-out (§1B C2): the
    same plaintext URL then boots."""
    _serving_config(monkeypatch, database_url=_SYNTHETIC_DB_URL)
    monkeypatch.setattr(settings, "database_tls_required", False)
    with TestClient(create_app()) as booted:
        assert booted.get("/healthz").status_code == 200
