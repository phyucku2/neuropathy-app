"""Tests for lab ingestion mapping (ADR-0006/0007): FHIR-aligned result -> research-grade
Observation row with provenance and correct coding.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.ingestion.labs import lab_result_to_observation
from app.models.observation import DataOrigin, ObservationStatus, SourceType
from app.schemas.lab import Interpretation, LabResultIn, LabStatus, ReferenceRange


def _result() -> LabResultIn:
    return LabResultIn(
        loinc_code="4548-4",
        display="Hemoglobin A1c",
        value=7.2,
        unit="%",
        effective_at=datetime(2026, 5, 1, tzinfo=UTC),
        reference_range=ReferenceRange(low=4.0, high=5.6, unit="%"),
        interpretation=Interpretation.high,
    )


def test_maps_to_research_grade_observation() -> None:
    pid = uuid4()
    obs = lab_result_to_observation(
        _result(),
        patient_id=pid,
        origin=DataOrigin.ehr_imported,
        recorded_by_role="patient",
        quality={"source_system": "Epic", "human_confirmed": True},
    )
    assert obs.patient_id == pid
    assert obs.source is SourceType.lab
    assert obs.origin is DataOrigin.ehr_imported
    assert obs.code == "4548-4"
    assert obs.code_system == "http://loinc.org"
    assert obs.unit_system == "http://unitsofmeasure.org"
    assert obs.value_num == 7.2
    assert obs.status is ObservationStatus.final
    assert obs.recorded_by_role == "patient"
    assert obs.quality["source_system"] == "Epic"
    # Provenance detail preserved in payload
    assert obs.payload["interpretation"] == "H"
    assert obs.payload["reference_range"]["high"] == 5.6


def test_preliminary_status_carries_through() -> None:
    r = _result()
    r.status = LabStatus.preliminary  # e.g. OCR'd, not yet confirmed
    obs = lab_result_to_observation(
        r, patient_id=uuid4(), origin=DataOrigin.document_imported, recorded_by_role="patient"
    )
    assert obs.status is ObservationStatus.preliminary


def test_recorded_at_defaults_to_now() -> None:
    before = datetime.now(UTC)
    obs = lab_result_to_observation(
        _result(), patient_id=uuid4(), origin=DataOrigin.ehr_imported, recorded_by_role="system"
    )
    assert obs.recorded_at >= before
