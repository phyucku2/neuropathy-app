"""Tests for the production HTTP transport using httpx.MockTransport (no network)."""

from __future__ import annotations

import httpx

from app.emr.transport import HttpxTransport


def _mock_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


async def test_get_json_sends_bearer_and_fhir_accept() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok"
        assert "application/fhir+json" in request.headers["Accept"]
        return httpx.Response(200, json={"ok": True})

    transport = HttpxTransport(client=_mock_client(httpx.MockTransport(handler)))
    assert await transport.get_json("https://ehr.example/fhir/Observation", access_token="tok") == {
        "ok": True
    }


async def test_get_json_without_token_has_no_auth_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"smart": "config"})

    transport = HttpxTransport(client=_mock_client(httpx.MockTransport(handler)))
    result = await transport.get_json("https://ehr.example/.well-known/smart-configuration")
    assert result == {"smart": "config"}


async def test_post_form_sends_urlencoded_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
        assert b"grant_type=authorization_code" in request.content
        return httpx.Response(200, json={"access_token": "tok"})

    transport = HttpxTransport(client=_mock_client(httpx.MockTransport(handler)))
    result = await transport.post_form(
        "https://ehr.example/oauth/token", {"grant_type": "authorization_code"}
    )
    assert result == {"access_token": "tok"}


async def test_http_errors_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_token"})

    transport = HttpxTransport(client=_mock_client(httpx.MockTransport(handler)))
    try:
        await transport.get_json("https://ehr.example/fhir/Observation", access_token="bad")
        raise AssertionError("expected HTTPStatusError")
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 401
