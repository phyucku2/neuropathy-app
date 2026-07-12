"""EMR FHIR client — fetches the patient's lab Observations and parses them (ADR-0008).

The HTTP transport is injected (a Protocol) so the fetch/parse logic is unit-tested with
a fake, and the real implementation (httpx, retries, paging, auth header) is swappable
without touching this logic.
"""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urlencode

from app.fhir.mapping import bundle_from_fhir
from app.fhir.resources import Bundle
from app.schemas.lab import LabResultIn


class FhirTransport(Protocol):
    """Minimal transport: GET a FHIR URL with a bearer token, return parsed JSON."""

    async def get_json(self, url: str, *, access_token: str) -> dict[str, Any]: ...


class EmrClient:
    def __init__(self, fhir_base: str, transport: FhirTransport) -> None:
        self._fhir_base = fhir_base.rstrip("/")
        self._transport = transport

    async def fetch_lab_observations(
        self, *, patient_fhir_id: str, access_token: str
    ) -> list[LabResultIn]:
        """Fetch laboratory Observations for the patient and map them to lab results.

        Follows Bundle `next` links to page through all results.
        """
        query = urlencode({"patient": patient_fhir_id, "category": "laboratory"})
        url: str | None = f"{self._fhir_base}/Observation?{query}"
        results: list[LabResultIn] = []

        while url:
            payload = await self._transport.get_json(url, access_token=access_token)
            bundle = Bundle.model_validate(payload)
            results.extend(bundle_from_fhir(bundle))
            url = _next_link(payload)

        return results


def _next_link(bundle_payload: dict[str, Any]) -> str | None:
    """Return the Bundle.link[relation=next].url, if any (FHIR paging)."""
    for link in bundle_payload.get("link", []):
        if link.get("relation") == "next":
            next_url = link.get("url")
            return next_url if isinstance(next_url, str) else None
    return None
