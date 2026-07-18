"""EMR FHIR client — fetches the patient's lab Observations and parses them (ADR-0008).

The HTTP transport is injected (a Protocol) so the fetch/parse logic is unit-tested with
a fake, and the real implementation (httpx, retries, paging, auth header) is swappable
without touching this logic.
"""

from __future__ import annotations

import time
from typing import Any, Protocol
from urllib.parse import urlencode

from app.fhir.mapping import lab_results_from_bundle_payload
from app.schemas.lab import LabResultIn

# Bounds on the FHIR paging loop (sweep #4): a slow, huge, or pathological EHR (e.g. one
# that always advertises a `next` link, or a self-referential next URL) must not pin a
# worker + its pooled DB connection indefinitely. Stop with a graceful 502 EmrError when
# either bound is exceeded, rather than looping forever.
MAX_LAB_PAGES = 100
LAB_PULL_DEADLINE_SECONDS = 60.0


class FhirTransport(Protocol):
    """Minimal transport: GET a FHIR URL with a bearer token, return parsed JSON."""

    async def get_json(self, url: str, *, access_token: str) -> dict[str, Any]: ...


class EmrClient:
    def __init__(self, fhir_base: str, transport: FhirTransport) -> None:
        self._fhir_base = fhir_base.rstrip("/")
        self._transport = transport

    async def fetch_lab_observations(
        self, *, patient_fhir_id: str, access_token: str
    ) -> tuple[list[LabResultIn], int]:
        """Fetch laboratory Observations for the patient and map them to lab results.

        Follows Bundle `next` links to page through all results. Parsing is LENIENT
        (`lab_results_from_bundle_payload`): un-mappable entries are skipped, not fatal, so a
        single non-final/panel/non-LOINC/OperationOutcome entry can't abort the whole pull.
        Returns ``(results, skipped_count)``.
        """
        # Local import breaks the service<->client import cycle (service.py builds EmrClient).
        from app.emr.service import EmrError

        query = urlencode({"patient": patient_fhir_id, "category": "laboratory"})
        url: str | None = f"{self._fhir_base}/Observation?{query}"
        results: list[LabResultIn] = []
        skipped = 0
        pages = 0
        started = time.monotonic()

        while url:
            pages += 1
            if pages > MAX_LAB_PAGES:
                raise EmrError(
                    "Your health record returned an unexpectedly large number of pages; "
                    "please try again later",
                    status_code=502,
                )
            if time.monotonic() - started > LAB_PULL_DEADLINE_SECONDS:
                raise EmrError(
                    "Fetching your labs from your health record took too long; "
                    "please try again later",
                    status_code=502,
                )
            payload = await self._transport.get_json(url, access_token=access_token)
            page_results, page_skipped = lab_results_from_bundle_payload(payload)
            results.extend(page_results)
            skipped += page_skipped
            url = _next_link(payload)

        return results, skipped


def _next_link(bundle_payload: dict[str, Any]) -> str | None:
    """Return the Bundle.link[relation=next].url, if any (FHIR paging)."""
    for link in bundle_payload.get("link", []):
        if link.get("relation") == "next":
            next_url = link.get("url")
            return next_url if isinstance(next_url, str) else None
    return None
