"""Bidirectional mapping between our LabResultIn and FHIR R4 Observation (ADR-0007).

FHIR uses hyphenated status codes (`entered-in-error`) and layered CodeableConcepts;
this module is the single place those representations meet. Field-by-field reference:
docs/engineering/fhir-mapping.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

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
from app.schemas.emr import ClinicalNoteIn
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
    """Extract all lab results from a FHIR Bundle of Observations (strict — raises on any
    un-mappable entry). Used for round-trip mapping of data WE produced; for parsing an
    external EHR search-set, use `lab_results_from_bundle_payload` (lenient)."""
    return [from_fhir(entry.resource) for entry in bundle.entry]


def lab_results_from_bundle_payload(payload: Mapping[str, Any]) -> tuple[list[LabResultIn], int]:
    """Resiliently map an EHR search-set Bundle payload to lab results (ADR-0007/0008).

    A real EHR ``Observation?category=laboratory`` search-set routinely contains entries we
    cannot or should not import: a non-final status (``registered``/``cancelled``/``unknown``),
    a panel/grouping Observation with no value, a lab coded only in a local (non-LOINC) system,
    a missing unit or effectiveDateTime, or a non-Observation entry such as an ``OperationOutcome``.
    Each such entry is **skipped**, never aborting the batch — the same reject-not-crash posture
    as the BioMech and wearable ingestion paths, so one bad row can't poison every valid row.
    No fabrication: a skipped entry simply does not enter the dataset.

    Returns ``(results, skipped_count)``. Bundle paging is handled by the caller via the raw
    payload's ``link`` (this function never touches the network).
    """
    results: list[LabResultIn] = []
    skipped = 0
    entries = payload.get("entry")
    for entry in entries if isinstance(entries, list) else []:
        resource = entry.get("resource") if isinstance(entry, Mapping) else None
        if not isinstance(resource, Mapping) or resource.get("resourceType") != "Observation":
            skipped += 1  # OperationOutcome or any non-Observation search-set entry
            continue
        try:
            results.append(from_fhir(Observation.model_validate(resource)))
        except (ValueError, ValidationError):
            skipped += 1  # unmappable Observation (bad status / no value / non-LOINC / no time)
    return results, skipped


def _parse_fhir_instant(value: Any) -> datetime:
    """Parse a FHIR dateTime/instant string to a tz-aware UTC datetime (naive -> UTC).

    Raises ValueError on a missing/empty/malformed value so the lenient note parser skips
    the entry rather than aborting the batch."""
    if not isinstance(value, str) or not value:
        raise ValueError("DocumentReference has no usable date")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _document_reference_to_note(resource: Mapping[str, Any]) -> ClinicalNoteIn:
    """Map ONE FHIR DocumentReference to a metadata-only note; raise ValueError when a
    required element (type, date, or a content attachment) is absent. NEVER touches body
    text — only references and metadata."""
    authored_at = _parse_fhir_instant(resource.get("date"))

    type_code: str | None = None
    type_display: str | None = None
    type_concept = resource.get("type")
    if isinstance(type_concept, Mapping):
        codings = type_concept.get("coding")
        if isinstance(codings, list) and codings and isinstance(codings[0], Mapping):
            first = codings[0]
            type_code = first.get("code") if isinstance(first.get("code"), str) else None
            type_display = first.get("display") if isinstance(first.get("display"), str) else None
        text_val = type_concept.get("text")
        type_display = type_display or (text_val if isinstance(text_val, str) else None)
    if not type_code and not type_display:
        raise ValueError("DocumentReference has no type")

    content = resource.get("content")
    if not isinstance(content, list) or not content or not isinstance(content[0], Mapping):
        raise ValueError("DocumentReference has no content")
    attachment = content[0].get("attachment")
    if not isinstance(attachment, Mapping):
        raise ValueError("DocumentReference content has no attachment")
    url = attachment.get("url")
    data = attachment.get("data")
    if not (isinstance(url, str) and url) and not data:
        raise ValueError("DocumentReference attachment has neither url nor inline data")

    author_display: str | None = None
    authors = resource.get("author")
    if isinstance(authors, list) and authors and isinstance(authors[0], Mapping):
        candidate = authors[0].get("display")
        author_display = candidate if isinstance(candidate, str) else None

    encounter_fhir_id: str | None = None
    context = resource.get("context")
    if isinstance(context, Mapping):
        encounters = context.get("encounter")
        if isinstance(encounters, list) and encounters and isinstance(encounters[0], Mapping):
            reference = encounters[0].get("reference")
            if isinstance(reference, str) and reference:
                encounter_fhir_id = reference.split("/")[-1]

    content_type = attachment.get("contentType")
    document_id = resource.get("id")
    return ClinicalNoteIn(
        document_fhir_id=document_id if isinstance(document_id, str) else None,
        type_code=type_code,
        type_display=type_display,
        authored_at=authored_at,
        author_display=author_display,
        encounter_fhir_id=encounter_fhir_id,
        content_type=content_type if isinstance(content_type, str) else None,
        attachment_url=url if isinstance(url, str) and url else None,
        has_inline_data=bool(data),
    )


def clinical_notes_from_bundle_payload(
    payload: Mapping[str, Any],
) -> tuple[list[ClinicalNoteIn], int]:
    """Resiliently map an EHR search-set Bundle of DocumentReferences to note metadata
    (ADR-0045 P2 #27).

    A real ``DocumentReference?category=clinical-note`` search-set mixes importable notes
    with entries we cannot or should not map: a non-DocumentReference entry (e.g. an
    ``OperationOutcome``), or a DocumentReference missing its type, date, or a content
    attachment. Each such entry is **skipped**, never aborting the batch — the same
    reject-not-crash posture as the lab parser. No body text is ever read.

    Returns ``(notes, skipped_count)``. Bundle paging is handled by the caller via the raw
    payload's ``link`` (this function never touches the network).
    """
    notes: list[ClinicalNoteIn] = []
    skipped = 0
    entries = payload.get("entry")
    for entry in entries if isinstance(entries, list) else []:
        resource = entry.get("resource") if isinstance(entry, Mapping) else None
        if not isinstance(resource, Mapping) or resource.get("resourceType") != "DocumentReference":
            skipped += 1  # OperationOutcome or any non-DocumentReference search-set entry
            continue
        try:
            notes.append(_document_reference_to_note(resource))
        except (ValueError, ValidationError, KeyError, TypeError):
            skipped += 1  # unmappable DocumentReference (no type / date / attachment)
    return notes, skipped
