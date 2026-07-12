"""HTTP transport for EMR calls — the one place real network I/O happens (ADR-0009).

`HttpTransport` is the protocol the service/client code depends on; `HttpxTransport` is
the production implementation. Tests inject fakes (or httpx.MockTransport) — no network
in CI.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx


class HttpTransport(Protocol):
    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]: ...

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]: ...


class HttpxTransport:
    """Production transport. Never logs URLs with tokens or response bodies (PHI)."""

    def __init__(self, client: httpx.AsyncClient | None = None, timeout_s: float = 20.0) -> None:
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        headers = {"Accept": "application/fhir+json, application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        response = await self._client.get(url, headers=headers)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        response = await self._client.post(url, data=data, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload
