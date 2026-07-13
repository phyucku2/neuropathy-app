"""Map a parsed BioMech report to research-grade Observations (ADR-0006, ADR-0014).

Mirrors the lab adapter: pure mapping functions (fully unit-tested), content-identity
idempotency, and full provenance. Every row is source=biomech, origin=document_imported
(the value was extracted from an imported document, not measured by a device on our
side — device_measured is reserved for the V2 API/SDK path, ADR-0014). `quality` names
how the datum came to exist: the source system, that it came from PDF text, and the
report kind. The import key is the report's content identity, so re-uploading the same
report is idempotent (skipped, never duplicated).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.biomech.parser import BiomechMetric, BiomechReport, ReportKind
from app.fhir.resources import UCUM_SYSTEM
from app.models.observation import (
    DataOrigin,
    Observation,
    ObservationStatus,
    SourceType,
)

# Names the ingest provenance in every row's quality dict (data-standards.md).
_SOURCE_SYSTEM = "BioMech"
_EXTRACTION = "pdf_text"


def _as_utc(value: datetime) -> datetime:
    """Naive assessment datetimes are assumed UTC (timezone handling like labs), so
    every stored effective_at is tz-aware and trend math never mixes naive and aware."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def biomech_import_key(kind: ReportKind, assessment_at: datetime, metric: BiomechMetric) -> str:
    """Stable idempotency key for one metric of one report: its content identity
    (report kind + assessment datetime + code + value + unit), mirroring
    `lab_import_key`. Re-uploading the same report yields the same keys, so already-
    imported rows are skipped instead of double-counted in the analyzable dataset."""
    return (
        f"content:biomech:{kind.value}:{_as_utc(assessment_at).isoformat()}"
        f":{metric.code}:{metric.value}:{metric.unit}"
    )


def biomech_metric_to_observation(
    metric: BiomechMetric,
    *,
    kind: ReportKind,
    assessment_at: datetime,
    device: str | None,
    patient_id: uuid.UUID,
    import_key: str,
    recorded_at: datetime | None = None,
) -> Observation:
    """Map one accepted metric to a research-grade Observation row.

    source=biomech, origin=document_imported (extracted from an imported document),
    status=final, effective_at = the report's assessment datetime (naive -> UTC).
    Displays come only from the closed metric registry (never document free text);
    the device/source line, if any, is provenance in `quality`/`payload`, never a label.
    """
    quality: dict[str, object] = {
        "source_system": _SOURCE_SYSTEM,
        "extraction": _EXTRACTION,
        "report_kind": kind.value,
    }
    if device is not None:
        quality["device"] = device
    return Observation(
        patient_id=patient_id,
        source=SourceType.biomech,
        origin=DataOrigin.document_imported,
        # Internal friendly key (like the ADL codes); code_system stays null — BioMech
        # metrics are our controlled vocabulary, not LOINC.
        code=metric.code,
        code_system=None,
        value_num=metric.value,
        unit=metric.unit,
        unit_system=UCUM_SYSTEM,
        effective_at=_as_utc(assessment_at),
        recorded_at=recorded_at or datetime.now(UTC),
        status=ObservationStatus.final,
        recorded_by_role="patient",
        import_key=import_key,
        quality=quality,
        payload={"display": metric.display, "report_kind": kind.value},
    )


def is_ingestable(report: BiomechReport) -> bool:
    """A report can produce Observations only when it has a kind, an assessment
    datetime, and at least one accepted metric — otherwise there is nothing to write."""
    return report.kind is not None and report.assessment_at is not None and bool(report.metrics)
