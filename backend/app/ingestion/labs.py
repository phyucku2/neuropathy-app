"""Lab ingestion — turn a validated FHIR-aligned lab result into a research-grade
Observation row (ADR-0006, ADR-0007).

The mapping is a pure function so it's fully unit-tested; persistence (writing the rows
in a transaction with an audit event) is a thin service layer added when the DB is wired
in CI. Provenance is required, not optional (data-standards.md).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.fhir.resources import LOINC_SYSTEM, UCUM_SYSTEM
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.schemas.lab import LabResultIn, LabStatus

# Lab status (FHIR-aligned) maps 1:1 onto the Observation lifecycle status.
_STATUS_MAP: dict[LabStatus, ObservationStatus] = {
    LabStatus.preliminary: ObservationStatus.preliminary,
    LabStatus.final: ObservationStatus.final,
    LabStatus.amended: ObservationStatus.amended,
    LabStatus.corrected: ObservationStatus.corrected,
    LabStatus.entered_in_error: ObservationStatus.entered_in_error,
}


def lab_result_to_observation(
    result: LabResultIn,
    *,
    patient_id: uuid.UUID,
    origin: DataOrigin,
    recorded_by_role: str,
    quality: dict[str, Any] | None = None,
    recorded_at: datetime | None = None,
    import_key: str | None = None,
) -> Observation:
    """Map a FHIR-aligned lab result to a research-grade Observation row.

    `origin` distinguishes an OCR'd document (needs human confirm) from an EHR pull
    (authoritative). `quality` carries provenance detail (extraction confidence,
    source system, human_confirmed). `recorded_at` defaults to now (contemporaneous).
    """
    return Observation(
        patient_id=patient_id,
        source=SourceType.lab,
        origin=origin,
        code=result.loinc_code,
        code_system=LOINC_SYSTEM if result.code_system == "LOINC" else result.code_system,
        value_num=result.value,
        value_text=result.value_text,
        unit=result.unit,
        unit_system=UCUM_SYSTEM if result.unit_system == "UCUM" else result.unit_system,
        effective_at=result.effective_at,
        recorded_at=recorded_at or datetime.now(UTC),
        status=_STATUS_MAP[result.status],
        recorded_by_role=recorded_by_role,
        quality=quality or {},
        payload={
            "display": result.display,
            "source_record_id": result.source_record_id,
            "import_key": import_key,
            "reference_range": result.reference_range.model_dump()
            if result.reference_range
            else None,
            "interpretation": result.interpretation.value if result.interpretation else None,
            "issued_at": result.issued_at.isoformat() if result.issued_at else None,
        },
    )


def lab_import_key(result: LabResultIn, *, fhir_base: str | None = None) -> str:
    """Stable idempotency key for one imported lab record.

    EMR pulls pass `fhir_base` so the source's own FHIR Observation id (globally
    stable per source system) wins; patient uploads (and EMR records without ids)
    key on the result's clinical content identity, so re-importing the same panel
    never duplicates the analyzable dataset.
    """
    if fhir_base is not None and result.source_record_id:
        return f"fhir:{fhir_base}:{result.source_record_id}"
    return (
        f"content:{result.loinc_code}:{result.effective_at.isoformat()}"
        f":{result.value}:{result.unit}:{result.value_text}"
    )
