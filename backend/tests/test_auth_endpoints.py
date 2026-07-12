"""End-to-end tests for the auth endpoints (ADR-0010): register -> login -> me ->
refresh, plus the failure modes that matter.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_service
from app.main import app
from app.services.auth import AuthService


@pytest.fixture()
def client() -> Iterator[TestClient]:
    service = AuthService(secret="endpoint-test-secret")
    app.dependency_overrides[get_auth_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _register(client: TestClient, email: str = "pat@example.com") -> dict[str, str]:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": "a-strong-password", "display_name": "Pat"},
    )
    assert resp.status_code == 201
    body: dict[str, str] = resp.json()
    return body


def test_register_returns_tokens_and_me_works(client: TestClient) -> None:
    tokens = _register(client)
    assert tokens["token_type"] == "bearer"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "pat@example.com"
    assert body["role"] == "patient"
    assert body["patient_id"] is not None  # a patient record link is created
    assert "password" not in me.text and "hash" not in me.text


def test_duplicate_email_is_409(client: TestClient) -> None:
    _register(client)
    resp = client.post(
        "/auth/register",
        json={"email": "pat@example.com", "password": "another-pass-1", "display_name": "X"},
    )
    assert resp.status_code == 409


def test_email_is_case_insensitive(client: TestClient) -> None:
    _register(client)
    resp = client.post(
        "/auth/login", json={"email": "PAT@example.com", "password": "a-strong-password"}
    )
    assert resp.status_code == 200


def test_wrong_password_is_401_with_generic_error(client: TestClient) -> None:
    _register(client)
    resp = client.post("/auth/login", json={"email": "pat@example.com", "password": "nope-nope"})
    assert resp.status_code == 401
    # Same message as unknown email — no account enumeration.
    unknown = client.post("/auth/login", json={"email": "who@example.com", "password": "x" * 8})
    assert unknown.status_code == 401
    assert resp.json()["detail"] == unknown.json()["detail"]


def test_short_password_is_422(client: TestClient) -> None:
    resp = client.post(
        "/auth/register",
        json={"email": "short@example.com", "password": "short", "display_name": "S"},
    )
    assert resp.status_code == 422


def test_refresh_issues_new_access_token(client: TestClient) -> None:
    tokens = _register(client)
    resp = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


def test_access_token_is_rejected_by_refresh(client: TestClient) -> None:
    tokens = _register(client)
    resp = client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401


def test_me_without_token_is_401(client: TestClient) -> None:
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_garbage_token_is_401(client: TestClient) -> None:
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert resp.status_code == 401


def test_deleted_account_token_is_401(client: TestClient) -> None:
    tokens = _register(client, email="gone@example.com")
    service = app.dependency_overrides[get_auth_service]()
    # Reach into the in-memory repository to simulate account deletion.
    user = service.users._by_email.pop("gone@example.com")  # noqa: SLF001
    service.users._by_id.pop(user.id)  # noqa: SLF001
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert resp.status_code == 401


def test_refresh_for_deleted_account_is_401(client: TestClient) -> None:
    tokens = _register(client, email="gone2@example.com")
    service = app.dependency_overrides[get_auth_service]()
    user = service.users._by_email.pop("gone2@example.com")  # noqa: SLF001
    service.users._by_id.pop(user.id)  # noqa: SLF001
    resp = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 401


def test_default_auth_service_is_cached_singleton() -> None:
    from app.api.deps import get_auth_service as real_dep

    assert real_dep() is real_dep()


def test_configured_jwt_secret_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import deps
    from app.core.config import settings

    monkeypatch.setattr(settings, "jwt_secret", "configured-secret")
    deps._default_auth_service.cache_clear()  # noqa: SLF001 — reset the singleton
    try:
        assert deps.get_auth_service().secret == "configured-secret"
    finally:
        deps._default_auth_service.cache_clear()  # noqa: SLF001
