"""CORS is admitted for the native mobile shells only (ADR-0023).

The web app is served same-origin (nginx reverse-proxies the API), so it needs no CORS.
The Capacitor WebView loads the bundled SPA from a fixed local origin and calls the API
cross-origin, so exactly those origins — and no wildcard — are allow-listed. These tests
pin that contract: the Capacitor origin is admitted (preflight + actual request), an
unknown origin is not, and the allow-list stays free of `*`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app

_CAPACITOR_ORIGIN = "https://localhost"


def test_preflight_from_capacitor_origin_is_allowed() -> None:
    client = TestClient(create_app())
    resp = client.options(
        "/auth/login",
        headers={
            "Origin": _CAPACITOR_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == _CAPACITOR_ORIGIN


def test_actual_request_from_capacitor_origin_gets_allow_origin_header() -> None:
    client = TestClient(create_app())
    # The route itself may 401/422 without a body — CORS decoration happens regardless.
    resp = client.post("/auth/login", headers={"Origin": _CAPACITOR_ORIGIN}, json={})
    assert resp.headers.get("access-control-allow-origin") == _CAPACITOR_ORIGIN


def test_unknown_origin_is_not_admitted() -> None:
    client = TestClient(create_app())
    resp = client.options(
        "/auth/login",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # Starlette answers a disallowed preflight without the allow-origin header (the browser
    # then blocks the request); the header must never echo an off-list origin.
    assert resp.headers.get("access-control-allow-origin") is None


def test_allow_list_carries_both_shell_origins_and_no_wildcard() -> None:
    origins = [o.strip() for o in settings.mobile_app_origins.split(",") if o.strip()]
    assert "https://localhost" in origins  # Android WebView
    assert "capacitor://localhost" in origins  # iOS WKWebView
    assert "*" not in origins
