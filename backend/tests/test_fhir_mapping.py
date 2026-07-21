"""Tests for the FHIR R4 lab Observation mapping (ADR-0007, fhir-mapping.md):
round-trips, canonical-JSON parse, Bundle, status hyphenation, and required-element
validation.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.fhir.mapping import (
    bundle_from_fhir,
    bundle_to_fhir,
    from_fhir,
    to_fhir,
)
from app.fhir.resources import Observation
from app.schemas.lab import Interpretation, LabResultIn, LabStatus, ReferenceRange


def _hba1c() -> LabResultIn:
    return LabResultIn(
        loinc_code="4548-4",
        display="Hemoglobin A1c",
        value=7.2,
        unit="%",
        effective_at=datetime(2026, 5, 1, tzinfo=UTC),
        issued_at=datetime(2026, 5, 2, tzinfo=UTC),
        reference_range=ReferenceRange(low=4.0, high=5.6, unit="%"),
        interpretation=Interpretation.high,
    )


def test_export_emits_canonical_fhir() -> None:
    fhir = to_fhir(_hba1c(), subject_id="abc").to_fhir_json()
    assert fhir["resourceType"] == "Observation"
    assert fhir["status"] == "final"
    assert fhir["category"][0]["coding"][0]["code"] == "laboratory"
    assert fhir["code"]["coding"][0]["system"] == "http://loinc.org"
    assert fhir["code"]["coding"][0]["code"] == "4548-4"
    assert fhir["valueQuantity"] == {
        "value": 7.2,
        "unit": "%",
        "system": "http://unitsofmeasure.org",
        "code": "%",
    }
    assert fhir["subject"]["reference"] == "Patient/abc"
    assert fhir["interpretation"][0]["coding"][0]["code"] == "H"


def test_round_trip_preserves_fields() -> None:
    original = _hba1c()
    back = from_fhir(to_fhir(original))
    assert back.loinc_code == original.loinc_code
    assert back.value == original.value
    assert back.unit == original.unit
    assert back.effective_at == original.effective_at
    assert back.issued_at == original.issued_at
    assert back.status is original.status
    assert back.interpretation is Interpretation.high
    assert back.reference_range is not None
    assert back.reference_range.low == 4.0
    assert back.reference_range.high == 5.6


def test_parse_external_fhir_json() -> None:
    payload = {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [{"system": "http://loinc.org", "code": "2339-0", "display": "Glucose"}]
        },
        "effectiveDateTime": "2026-06-15T08:30:00+00:00",
        "valueQuantity": {
            "value": 95,
            "unit": "mg/dL",
            "system": "http://unitsofmeasure.org",
            "code": "mg/dL",
        },
        # An unknown element must be ignored, not rejected:
        "meta": {"versionId": "3"},
    }
    result = from_fhir(Observation.model_validate(payload))
    assert result.loinc_code == "2339-0"
    assert result.value == 95
    assert result.unit == "mg/dL"


def test_entered_in_error_status_hyphenation() -> None:
    r = _hba1c()
    r.status = LabStatus.entered_in_error
    fhir = to_fhir(r).to_fhir_json()
    assert fhir["status"] == "entered-in-error"
    assert from_fhir(to_fhir(r)).status is LabStatus.entered_in_error


def test_qualitative_value_string_round_trip() -> None:
    r = LabResultIn(
        loinc_code="5802-4",
        display="Nitrite",
        value_text="positive",
        effective_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    fhir = to_fhir(r).to_fhir_json()
    assert fhir["valueString"] == "positive"
    assert "valueQuantity" not in fhir
    assert from_fhir(to_fhir(r)).value_text == "positive"


def test_bundle_round_trip() -> None:
    results = [_hba1c(), _hba1c()]
    bundle = bundle_to_fhir(results, subject_id="p1")
    assert bundle.to_fhir_json()["type"] == "collection"
    parsed = bundle_from_fhir(bundle)
    assert len(parsed) == 2
    assert all(p.loinc_code == "4548-4" for p in parsed)


def test_interpretation_coding_without_code_is_ignored() -> None:
    payload = {
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4"}]},
        "effectiveDateTime": "2026-06-15T08:30:00+00:00",
        "valueQuantity": {
            "value": 7.2,
            "unit": "%",
            "system": "http://unitsofmeasure.org",
            "code": "%",
        },
        "interpretation": [{"coding": [{"system": "http://x", "display": "no code here"}]}],
    }
    result = from_fhir(Observation.model_validate(payload))
    assert result.interpretation is None


def test_import_without_loinc_raises() -> None:
    payload = {
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": [{"system": "http://example.org/local", "code": "X"}]},
        "effectiveDateTime": "2026-06-15T08:30:00+00:00",
        "valueQuantity": {
            "value": 1,
            "unit": "1",
            "system": "http://unitsofmeasure.org",
            "code": "1",
        },
    }
    with pytest.raises(ValueError, match="LOINC"):
        from_fhir(Observation.model_validate(payload))


def test_import_without_effective_time_raises() -> None:
    payload = {
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4"}]},
        "valueQuantity": {
            "value": 7.2,
            "unit": "%",
            "system": "http://unitsofmeasure.org",
            "code": "%",
        },
    }
    with pytest.raises(ValueError, match="effectiveDateTime"):
        from_fhir(Observation.model_validate(payload))


# --- Clinical-note DocumentReference parser (ADR-0045 P2 #27) --------------------------


def _doc_ref(**overrides: object) -> dict:
    base = {
        "resourceType": "DocumentReference",
        "id": "doc-1",
        "type": {
            "coding": [
                {"system": "http://loinc.org", "code": "11506-3", "display": "Progress note"}
            ]
        },
        "date": "2026-06-15T08:30:00Z",
        "author": [{"display": "Dr Synthetic"}],
        "context": {"encounter": [{"reference": "Encounter/enc-1"}]},
        "content": [{"attachment": {"contentType": "text/plain", "url": "https://ehr/Binary/b1"}}],
    }
    base.update(overrides)
    return base


def test_clinical_notes_parser_maps_metadata_only() -> None:
    from app.fhir.mapping import clinical_notes_from_bundle_payload

    payload = {"resourceType": "Bundle", "entry": [{"resource": _doc_ref()}]}
    notes, skipped = clinical_notes_from_bundle_payload(payload)
    assert skipped == 0 and len(notes) == 1
    note = notes[0]
    assert note.document_fhir_id == "doc-1"
    assert note.type_code == "11506-3"
    assert note.type_display == "Progress note"
    assert note.author_display == "Dr Synthetic"
    assert note.encounter_fhir_id == "enc-1"  # trailing id of the reference
    assert note.authored_at == datetime(2026, 6, 15, 8, 30, tzinfo=UTC)  # Z -> UTC
    assert note.attachment_url == "https://ehr/Binary/b1"


def test_clinical_notes_parser_skips_unmappable_and_counts() -> None:
    from app.fhir.mapping import clinical_notes_from_bundle_payload

    payload = {
        "resourceType": "Bundle",
        "entry": [
            {"resource": _doc_ref(id="ok")},  # good
            {"resource": _doc_ref(id="no-type", type={})},  # missing type
            {"resource": _doc_ref(id="no-date", date=None)},  # missing date
            {"resource": _doc_ref(id="no-attach", content=[])},  # missing attachment
            {"resource": {"resourceType": "OperationOutcome", "issue": []}},  # not a DocRef
        ],
    }
    notes, skipped = clinical_notes_from_bundle_payload(payload)
    assert [n.document_fhir_id for n in notes] == ["ok"]
    assert skipped == 4  # one bad entry never aborts the batch


def test_clinical_notes_parser_accepts_type_text_only_and_inline_data() -> None:
    from app.fhir.mapping import clinical_notes_from_bundle_payload

    resource = _doc_ref(
        id="text-only",
        type={"text": "Consult note"},  # no coding, only text
        content=[{"attachment": {"contentType": "text/plain", "data": "aGVsbG8="}}],  # inline
    )
    notes, skipped = clinical_notes_from_bundle_payload(
        {"resourceType": "Bundle", "entry": [{"resource": resource}]}
    )
    assert skipped == 0 and len(notes) == 1
    assert notes[0].type_display == "Consult note"
    assert notes[0].type_code is None
    assert notes[0].has_inline_data is True
    assert notes[0].attachment_url is None
