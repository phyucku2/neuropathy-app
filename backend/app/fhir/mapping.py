"""Bidirectional mapping between our LabResultIn and FHIR R4 Observation (ADR-0007).

FHIR uses hyphenated status codes (`entered-in-error`) and layered CodeableConcepts;
this module is the single place those representations meet. Field-by-field reference:
docs/engineering/fhir-mapping.md.
"""

from __future__ import annotations

from app.fhir.resources import (
    CATEGORY_SYSTEM,
    INTERPRETATION_SYSTEM,
    LOINC_SYSTEM,
    UCUM_SYSTEM,
    Bundle,
    CodeableConcept,
    Coding,
    Observation,
    ObservationReferenceRange,
    Quantity,
    Reference,
)
from app.schemas.lab import Interpretation, LabResultIn, LabStatus, ReferenceRange

_LABORATORY_CATEGORY = CodeableConcept(
    coding=[Coding(system=CATEGORY_SYSTEM, code="laboratory", display="Laboratory")]
)


def _status_to_fhir(status: LabStatus) -> str:
    return status.value.replace("_", "-")


def _status_from_fhir(status: str) -> LabStatus:
    return LabStatus(status.replace("-", "_"))


def to_fhir(result: LabResultIn, *, subject_id: str | None = None) -> Observation:
    """Map an internal lab result to a FHIR Observation (laboratory)."""
    value_quantity = None
    if result.value is not None:
        value_quantity = Quantity(
            value=result.value,
            unit=result.unit,
            system=UCUM_SYSTEM,
            code=result.unit,
        )

    reference_range = []
    if result.reference_range and (
        result.reference_range.low is not None or result.reference_range.high is not None
    ):
        rr = result.reference_range
        unit = rr.unit or result.unit
        reference_range = [
            ObservationReferenceRange(
                low=Quantity(value=rr.low, unit=unit, system=UCUM_SYSTEM, code=unit)
                if rr.low is not None
                else None,
                high=Quantity(value=rr.high, unit=unit, system=UCUM_SYSTEM, code=unit)
                if rr.high is not None
                else None,
            )
        ]

    interpretation = []
    if result.interpretation is not None:
        interpretation = [
            CodeableConcept(
                coding=[Coding(system=INTERPRETATION_SYSTEM, code=result.interpretation.value)]
            )
        ]

    return Observation(
        status=_status_to_fhir(result.status),
        category=[_LABORATORY_CATEGORY],
        code=CodeableConcept(
            coding=[Coding(system=LOINC_SYSTEM, code=result.loinc_code, display=result.display)],
            text=result.display,
        ),
        subject=Reference(reference=f"Patient/{subject_id}") if subject_id else None,
        effectiveDateTime=result.effective_at,
        issued=result.issued_at,
        valueQuantity=value_quantity,
        value_string=result.value_text,
        referenceRange=reference_range,
        interpretation=interpretation,
    )


def _loinc_coding(concept: CodeableConcept) -> Coding:
    for coding in concept.coding:
        if coding.system == LOINC_SYSTEM and coding.code:
            return coding
    raise ValueError("FHIR Observation.code has no LOINC coding")


def from_fhir(obs: Observation) -> LabResultIn:
    """Map a FHIR Observation (laboratory) to an internal lab result.

    Raises ValueError if required lab elements are missing (LOINC code, effective time,
    or any value).
    """
    coding = _loinc_coding(obs.code)
    if obs.effective_date_time is None:
        raise ValueError("FHIR Observation is missing effectiveDateTime")

    value = obs.value_quantity.value if obs.value_quantity else None
    unit = obs.value_quantity.unit or obs.value_quantity.code if obs.value_quantity else None

    reference_range = None
    if obs.reference_range:
        rr = obs.reference_range[0]
        reference_range = ReferenceRange(
            low=rr.low.value if rr.low else None,
            high=rr.high.value if rr.high else None,
            unit=(rr.low.unit if rr.low else None) or (rr.high.unit if rr.high else None),
        )

    interpretation = None
    if obs.interpretation and obs.interpretation[0].coding:
        code = obs.interpretation[0].coding[0].code
        if code is not None:
            interpretation = Interpretation(code)

    return LabResultIn(
        loinc_code=coding.code or "",
        source_record_id=obs.id,
        display=coding.display or obs.code.text or (coding.code or ""),
        value=value,
        value_text=obs.value_string,
        unit=unit,
        effective_at=obs.effective_date_time,
        issued_at=obs.issued,
        status=_status_from_fhir(obs.status),
        reference_range=reference_range,
        interpretation=interpretation,
    )


def bundle_to_fhir(results: list[LabResultIn], *, subject_id: str | None = None) -> Bundle:
    """Pack multiple lab results into a FHIR collection Bundle."""
    from app.fhir.resources import BundleEntry

    return Bundle(entry=[BundleEntry(resource=to_fhir(r, subject_id=subject_id)) for r in results])


def bundle_from_fhir(bundle: Bundle) -> list[LabResultIn]:
    """Extract all lab results from a FHIR Bundle of Observations."""
    return [from_fhir(entry.resource) for entry in bundle.entry]
