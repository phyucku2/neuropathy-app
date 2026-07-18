"""Tests for the EMR FHIR client (ADR-0008): fetch + parse lab Observations, with paging,
using a fake transport (no network).
"""

from __future__ import annotations

from typing import Any

from app.emr.client import EmrClient


class FakeTransport:
    """Returns queued FHIR JSON payloads in order; records requested URLs."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages
        self.calls: list[str] = []

    async def get_json(self, url: str, *, access_token: str) -> dict[str, Any]:
        self.calls.append(url)
        return self._pages.pop(0)


def _observation(loinc: str, value: float) -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc}]},
        "effectiveDateTime": "2026-06-15T08:30:00+00:00",
        "valueQuantity": {
            "value": value,
            "unit": "mg/dL",
            "system": "http://unitsofmeasure.org",
            "code": "mg/dL",
        },
    }


async def test_fetch_parses_lab_observations() -> None:
    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": _observation("2339-0", 95)}],
    }
    client = EmrClient("https://ehr.example/fhir/", FakeTransport([bundle]))
    results, skipped = await client.fetch_lab_observations(patient_fhir_id="p1", access_token="tok")
    assert len(results) == 1
    assert skipped == 0
    assert results[0].loinc_code == "2339-0"
    assert results[0].value == 95


async def test_non_next_links_do_not_cause_extra_fetches() -> None:
    # A Bundle with only a 'self' link must terminate paging (no infinite loop).
    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "link": [{"relation": "self", "url": "https://ehr.example/fhir/Observation?page=1"}],
        "entry": [{"resource": _observation("2339-0", 95)}],
    }
    transport = FakeTransport([bundle])
    client = EmrClient("https://ehr.example/fhir", transport)
    results, _ = await client.fetch_lab_observations(patient_fhir_id="p1", access_token="tok")
    assert len(results) == 1
    assert len(transport.calls) == 1


async def test_fetch_follows_next_paging_links() -> None:
    page1 = {
        "resourceType": "Bundle",
        "type": "searchset",
        "link": [{"relation": "next", "url": "https://ehr.example/fhir/Observation?page=2"}],
        "entry": [{"resource": _observation("2339-0", 95)}],
    }
    page2 = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": _observation("4548-4", 7.2)}],
    }
    transport = FakeTransport([page1, page2])
    client = EmrClient("https://ehr.example/fhir", transport)
    results, _ = await client.fetch_lab_observations(patient_fhir_id="p1", access_token="tok")
    assert [r.loinc_code for r in results] == ["2339-0", "4548-4"]
    # First request targets the laboratory-category search; second follows the next link.
    assert "category=laboratory" in transport.calls[0]
    assert transport.calls[1].endswith("page=2")


async def test_unmappable_entries_are_skipped_not_fatal() -> None:
    """A realistic EHR search-set mixes importable labs with entries we can't/shouldn't map:
    a non-final status, a panel Observation with no value, a non-LOINC code, and an
    OperationOutcome. One bad row must NOT abort the whole pull (sweep finding #1)."""
    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {"resource": _observation("2339-0", 95)},  # good
            {"resource": {**_observation("2339-0", 1), "status": "cancelled"}},  # non-final
            {
                "resource": {
                    "resourceType": "Observation",
                    "status": "final",  # panel, no value
                    "code": {"coding": [{"system": "http://loinc.org", "code": "58410-2"}]},
                    "effectiveDateTime": "2026-06-15T08:30:00+00:00",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "status": "final",  # non-LOINC only
                    "code": {"coding": [{"system": "urn:local", "code": "X"}]},
                    "effectiveDateTime": "2026-06-15T08:30:00+00:00",
                    "valueQuantity": {"value": 1, "unit": "mg/dL"},
                }
            },
            {"resource": {"resourceType": "OperationOutcome", "issue": []}},  # not an Observation
        ],
    }
    client = EmrClient("https://ehr.example/fhir", FakeTransport([bundle]))
    results, skipped = await client.fetch_lab_observations(patient_fhir_id="p1", access_token="tok")
    assert [r.loinc_code for r in results] == ["2339-0"]  # only the good row imported
    assert skipped == 4  # the other four skipped, no exception
