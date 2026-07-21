"""Tests for the EMR clinical-note client + lenient DocumentReference parser (ADR-0045 P2
#27): fetch + parse note METADATA, with paging + watermark, using a fake transport (no
network). Mirrors the five lab-client shapes; asserts no note body is ever read here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

import app.emr.notes_client as notes_client_module
from app.emr.notes_client import EmrClinicalNoteClient
from app.emr.service import EmrError
from app.fhir.mapping import clinical_notes_from_bundle_payload


class FakeTransport:
    """Returns queued FHIR JSON payloads in order; records requested URLs + tokens."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages
        self.calls: list[str] = []
        self.tokens: list[str | None] = []

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        self.calls.append(url)
        self.tokens.append(access_token)
        return self._pages.pop(0)


def _document_reference(
    doc_id: str,
    *,
    type_code: str = "11506-3",
    type_display: str = "Progress note",
    date: str = "2026-06-15T08:30:00+00:00",
    author: str | None = "Dr Synthetic",
    encounter: str | None = "Encounter/enc-1",
    url: str | None = "https://ehr.example/fhir/Binary/bin-1",
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "resourceType": "DocumentReference",
        "id": doc_id,
        "type": {
            "coding": [{"system": "http://loinc.org", "code": type_code, "display": type_display}]
        },
        "date": date,
        "content": [{"attachment": {"contentType": "text/plain", "url": url}}],
    }
    if author is not None:
        resource["author"] = [{"display": author}]
    if encounter is not None:
        resource["context"] = {"encounter": [{"reference": encounter}]}
    return resource


async def test_fetch_parses_document_reference_metadata() -> None:
    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": _document_reference("doc-1")}],
    }
    client = EmrClinicalNoteClient("https://ehr.example/fhir/", FakeTransport([bundle]))
    notes, skipped = await client.fetch_clinical_notes(patient_fhir_id="p1", access_token="tok")
    assert skipped == 0
    assert len(notes) == 1
    note = notes[0]
    assert note.document_fhir_id == "doc-1"
    assert note.type_code == "11506-3"
    assert note.type_display == "Progress note"
    assert note.author_display == "Dr Synthetic"
    assert note.encounter_fhir_id == "enc-1"
    assert note.authored_at == datetime(2026, 6, 15, 8, 30, tzinfo=UTC)
    assert note.attachment_url == "https://ehr.example/fhir/Binary/bin-1"


async def test_first_request_targets_the_clinical_note_category() -> None:
    bundle = {"resourceType": "Bundle", "type": "searchset", "entry": []}
    transport = FakeTransport([bundle])
    client = EmrClinicalNoteClient("https://ehr.example/fhir", transport)
    await client.fetch_clinical_notes(patient_fhir_id="p1", access_token="tok")
    assert "DocumentReference?" in transport.calls[0]
    assert "category=clinical-note" in transport.calls[0]
    assert "date=ge" not in transport.calls[0]  # no watermark on the first pull


async def test_watermark_bounds_the_search_with_date_ge() -> None:
    bundle = {"resourceType": "Bundle", "type": "searchset", "entry": []}
    transport = FakeTransport([bundle])
    client = EmrClinicalNoteClient("https://ehr.example/fhir", transport)
    watermark = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    await client.fetch_clinical_notes(patient_fhir_id="p1", access_token="tok", watermark=watermark)
    assert "date=ge2026-07-01T12" in transport.calls[0]  # incremental pull bound


async def test_non_next_links_do_not_cause_extra_fetches() -> None:
    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "link": [{"relation": "self", "url": "https://ehr.example/fhir/DocumentReference?page=1"}],
        "entry": [{"resource": _document_reference("doc-1")}],
    }
    transport = FakeTransport([bundle])
    client = EmrClinicalNoteClient("https://ehr.example/fhir", transport)
    notes, _ = await client.fetch_clinical_notes(patient_fhir_id="p1", access_token="tok")
    assert len(notes) == 1
    assert len(transport.calls) == 1


async def test_fetch_follows_next_paging_links() -> None:
    page1 = {
        "resourceType": "Bundle",
        "type": "searchset",
        "link": [{"relation": "next", "url": "https://ehr.example/fhir/DocumentReference?page=2"}],
        "entry": [{"resource": _document_reference("doc-1")}],
    }
    page2 = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": _document_reference("doc-2")}],
    }
    transport = FakeTransport([page1, page2])
    client = EmrClinicalNoteClient("https://ehr.example/fhir", transport)
    notes, _ = await client.fetch_clinical_notes(patient_fhir_id="p1", access_token="tok")
    assert [n.document_fhir_id for n in notes] == ["doc-1", "doc-2"]
    assert "category=clinical-note" in transport.calls[0]
    assert transport.calls[1].endswith("page=2")


async def test_unmappable_entries_are_skipped_not_fatal() -> None:
    """A realistic search-set mixes importable notes with entries we can't map: a
    DocumentReference with no type, one with no date, one with no attachment, and an
    OperationOutcome. One bad entry must NOT abort the whole pull."""
    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {"resource": _document_reference("doc-1")},  # good
            {"resource": {**_document_reference("doc-2"), "type": {}}},  # no type
            {"resource": {**_document_reference("doc-3"), "date": None}},  # no date
            {"resource": {**_document_reference("doc-4"), "content": []}},  # no attachment
            {"resource": {"resourceType": "OperationOutcome", "issue": []}},  # not a DocRef
        ],
    }
    client = EmrClinicalNoteClient("https://ehr.example/fhir", FakeTransport([bundle]))
    notes, skipped = await client.fetch_clinical_notes(patient_fhir_id="p1", access_token="tok")
    assert [n.document_fhir_id for n in notes] == ["doc-1"]  # only the good one
    assert skipped == 4


class _AlwaysNext:
    """A pathological EHR that ALWAYS advertises a next link — an unbounded loop trap."""

    def __init__(self) -> None:
        self.calls = 0

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        self.calls += 1
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "link": [
                {"relation": "next", "url": "https://ehr.example/fhir/DocumentReference?page=n"}
            ],
            "entry": [{"resource": _document_reference("doc-x")}],
        }


async def test_pagination_is_bounded_against_a_pathological_ehr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notes_client_module, "MAX_NOTE_PAGES", 3)
    transport = _AlwaysNext()
    client = EmrClinicalNoteClient("https://ehr.example/fhir", transport)
    with pytest.raises(EmrError) as exc:
        await client.fetch_clinical_notes(patient_fhir_id="p1", access_token="tok")
    assert exc.value.status_code == 502
    assert transport.calls == 3  # stopped at the bound; did not loop forever


async def test_body_fetch_uses_the_bearer_and_is_a_separate_call() -> None:
    """The note body is fetched LAZILY via the Binary reference — with the bearer, and
    NEVER during the poll. The transport records the token that was presented."""
    transport = FakeTransport(
        [{"resourceType": "Binary", "contentType": "text/plain", "data": "..."}]
    )
    client = EmrClinicalNoteClient("https://ehr.example/fhir", transport)
    body = await client.fetch_note_body(
        attachment_url="https://ehr.example/fhir/Binary/bin-1", access_token="the-bearer"
    )
    assert transport.tokens == ["the-bearer"]  # bearer presented on the body fetch
    assert transport.calls == ["https://ehr.example/fhir/Binary/bin-1"]
    assert body["resourceType"] == "Binary"


@pytest.mark.parametrize(
    "attachment_url",
    [
        "https://evil.example/exfiltrate",  # attacker host
        "http://ehr.example/fhir/Binary/bin-1",  # scheme downgrade, same host
        "https://ehr.example:8443/fhir/Binary/bin-1",  # same host, different port
        "http://169.254.169.254/latest/meta-data",  # cloud metadata (SSRF)
    ],
)
async def test_body_fetch_refuses_cross_origin_attachment_urls(attachment_url: str) -> None:
    """attachment_url is EHR-supplied data stored verbatim: a URL whose origin differs
    from the connection's fhir_base must be refused BEFORE any request is made — the
    bearer (the patient's live EMR access token) is never presented to another host,
    and internal addresses never become fetchable server-side."""
    transport = FakeTransport([])
    client = EmrClinicalNoteClient("https://ehr.example/fhir", transport)
    with pytest.raises(EmrError) as exc:
        await client.fetch_note_body(attachment_url=attachment_url, access_token="the-bearer")
    assert exc.value.status_code == 502
    assert "not hosted by your connected health record" in exc.value.reason
    assert transport.calls == []  # NO request was made — the token never left the app
    assert transport.tokens == []


class _HttpxErrorTransport:
    """A transport that fails the way the real one does: an httpx error whose message
    embeds the FULL request URL (patient FHIR id and all)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        import httpx

        self.calls.append(url)
        request = httpx.Request("GET", url)
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError(
            f"Client error '429 Too Many Requests' for url '{url}'",
            request=request,
            response=response,
        )


async def test_ehr_http_errors_are_wrapped_phi_free() -> None:
    """An EHR 4xx/5xx mid-pull must surface as the module's typed EmrError with a STATIC
    message: httpx's own exception text carries the full search URL — including the
    patient's EHR FHIR id (MBI-adjacent) — which must never reach server logs via an
    unhandled traceback."""
    transport = _HttpxErrorTransport()
    client = EmrClinicalNoteClient("https://ehr.example/fhir", transport)
    with pytest.raises(EmrError) as exc:
        await client.fetch_clinical_notes(
            patient_fhir_id="fhir-patient-9", access_token="the-bearer"
        )
    assert exc.value.status_code == 502
    rendered = str(exc.value)
    assert "fhir-patient-9" not in rendered  # no patient FHIR id
    assert "ehr.example" not in rendered  # no URL fragments at all
    assert exc.value.__cause__ is None  # chain broken: the URL-bearing httpx error
    assert exc.value.__suppress_context__  # cannot be rendered from this exception

    # The lazy body fetch takes the same PHI-free wrapping.
    with pytest.raises(EmrError) as body_exc:
        await client.fetch_note_body(
            attachment_url="https://ehr.example/fhir/Binary/bin-1", access_token="the-bearer"
        )
    assert body_exc.value.status_code == 502
    assert "Binary" not in str(body_exc.value)


def test_parser_reads_no_body_field() -> None:
    """The lenient parser produces metadata only — the parsed note has no body/text field
    even when the attachment carries inline data."""
    payload = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "DocumentReference",
                    "id": "doc-inline",
                    "type": {"text": "Consult note"},
                    "date": "2026-06-15T08:30:00Z",
                    "content": [
                        {"attachment": {"contentType": "text/plain", "data": "SECRET-BODY"}}
                    ],
                }
            }
        ],
    }
    notes, skipped = clinical_notes_from_bundle_payload(payload)
    assert skipped == 0
    assert len(notes) == 1
    note = notes[0]
    assert note.type_display == "Consult note"
    assert note.has_inline_data is True  # inline data was DETECTED
    assert note.attachment_url is None
    # The body text itself is never carried on the parsed note.
    assert "SECRET-BODY" not in note.model_dump_json()
