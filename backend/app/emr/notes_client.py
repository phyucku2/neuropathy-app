"""EMR clinical-note client — fetches DocumentReference metadata and pages it (ADR-0045 P2).

Sibling of ``app.emr.client.EmrClient`` (labs). The HTTP transport is injected (a
Protocol) so the fetch/parse logic is unit-tested with a fake; the real implementation
(httpx, auth header) is swappable. Parsing is LENIENT
(``clinical_notes_from_bundle_payload``): un-mappable entries are skipped, never fatal.

NON-DIAGNOSTIC: this pulls DocumentReference METADATA only. The note body is fetched
lazily and separately via ``fetch_note_body`` (the Binary reference), never during the
poll, and never summarized or fed to the narrator.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from app.emr.client import FhirTransport, _next_link
from app.fhir.mapping import clinical_notes_from_bundle_payload
from app.schemas.emr import ClinicalNoteIn

# Bounds on the FHIR paging loop (mirrors the lab bounds): a slow, huge, or pathological
# EHR (e.g. one that always advertises a `next` link) must not pin a worker + its pooled
# DB connection indefinitely. Stop with a graceful 502 EmrError when a bound is exceeded.
MAX_NOTE_PAGES = 100
NOTE_PULL_DEADLINE_SECONDS = 60.0


class EmrClinicalNoteClient:
    def __init__(self, fhir_base: str, transport: FhirTransport) -> None:
        self._fhir_base = fhir_base.rstrip("/")
        self._transport = transport

    async def fetch_clinical_notes(
        self,
        *,
        patient_fhir_id: str,
        access_token: str,
        watermark: datetime | None = None,
    ) -> tuple[list[ClinicalNoteIn], int]:
        """Fetch clinical-note DocumentReferences for the patient and map their metadata.

        Follows Bundle ``next`` links to page through all results. When ``watermark`` is
        set (the connection's ``last_notes_pulled_at``), the search is bounded with
        ``date=ge{watermark}`` so a re-pull only fetches notes authored since the last
        sync. Returns ``(notes, skipped_count)``.
        """
        # Local import breaks the service<->client import cycle (service builds this client).
        from app.emr.service import EmrError

        params = {"patient": patient_fhir_id, "category": "clinical-note"}
        if watermark is not None:
            params["date"] = f"ge{watermark.isoformat()}"
        query = urlencode(params)
        url: str | None = f"{self._fhir_base}/DocumentReference?{query}"
        notes: list[ClinicalNoteIn] = []
        skipped = 0
        pages = 0
        started = time.monotonic()

        while url:
            pages += 1
            if pages > MAX_NOTE_PAGES:
                raise EmrError(
                    "Your health record returned an unexpectedly large number of pages; "
                    "please try again later",
                    status_code=502,
                )
            if time.monotonic() - started > NOTE_PULL_DEADLINE_SECONDS:
                raise EmrError(
                    "Fetching your clinical notes from your health record took too long; "
                    "please try again later",
                    status_code=502,
                )
            payload = await self._transport.get_json(url, access_token=access_token)
            page_notes, page_skipped = clinical_notes_from_bundle_payload(payload)
            notes.extend(page_notes)
            skipped += page_skipped
            url = _next_link(payload)

        return notes, skipped

    async def fetch_note_body(self, *, attachment_url: str, access_token: str) -> dict[str, Any]:
        """Lazily fetch ONE note's Binary body on demand (never during the poll).

        The bearer is presented via the shared transport (which sets ``Authorization:
        Bearer``). The returned payload is handed straight to the caller to surface as the
        VERBATIM note — it is never summarized, logged, or written into a summary/audit."""
        return await self._transport.get_json(attachment_url, access_token=access_token)
