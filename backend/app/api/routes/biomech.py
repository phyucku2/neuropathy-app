"""BioMech report upload — the V1 ingest surface (ADR-0014).

BioMech Health runs their own apps; we only INGEST and GRAPH the balance/gait report
PDFs their portal exports. This route mirrors the lab intake pattern (routes/
ingestion.py): ownership comes from the authenticated patient (never the body), the
capability gate refuses the write when the feature is off (409), extraction/parsing/
mapping live in app/biomech, storage is the shared observation repository on
EmrServiceDep, and the PHI write is audit-logged with counts + report kind only —
never a value.

Uploaded metrics land as research-grade Observations (source=biomech), so they appear
in GET /observations and the trajectory automatically. Re-uploading the same report is
idempotent per content identity (skipped, not duplicated).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.deps import EmrServiceDep, PatientUserDep, require_capability
from app.biomech.ingest import (
    biomech_import_key,
    biomech_metric_to_observation,
    is_ingestable,
)
from app.biomech.parser import parse_report
from app.biomech.pdf import BiomechPdfError, extract_text
from app.core.config import settings
from app.models.audit import AuditEvent
from app.schemas.biomech import BiomechImportOut

router = APIRouter(tags=["biomech"])


@router.post(
    "/biomech/reports",
    response_model=BiomechImportOut,
    dependencies=[Depends(require_capability("ingest_biomech"))],
)
async def import_biomech_report(
    current: PatientUserDep,
    service: EmrServiceDep,
    file: Annotated[UploadFile, File(description="A BioMech balance or gait report PDF")],
) -> BiomechImportOut:
    """Ingest one BioMech balance/gait report PDF as research-grade Observations.

    Text-layer extraction only (no OCR, no rendering); a non-PDF, oversized, or
    unreadable upload is a 422. Parsing is defensive: unknown lines are ignored and
    non-numeric or out-of-range metrics are skipped with a warning. Idempotent per
    report content identity.
    """
    assert current.patient_id is not None  # guaranteed by require_patient
    max_bytes = settings.biomech_max_pdf_bytes
    # Starlette has already spooled the multipart part, so `size` is the actual byte
    # count: reject an oversized upload before ANY of it is materialized in memory
    # (review finding: a cap that fires after full buffering bounds nothing).
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(status_code=422, detail=f"PDF exceeds the {max_bytes}-byte size cap")
    # Bounded read even when size is unknown: at most cap+1 bytes reach memory, and
    # extract_text rejects the overflow byte.
    data = await file.read(max_bytes + 1)
    try:
        # pypdf is synchronous — a worker thread keeps extraction (the expensive step
        # of this request) off the event loop (review finding).
        text = await run_in_threadpool(extract_text, data)
    except BiomechPdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    report = parse_report(text)
    warnings = list(report.warnings)
    imported = 0
    skipped = 0

    if is_ingestable(report):
        assert report.kind is not None and report.assessment_at is not None  # is_ingestable
        keys = [
            biomech_import_key(report.kind, report.assessment_at, metric, report.condition)
            for metric in report.metrics
        ]
        # ONE existence probe for the whole report (indexed column), not N queries.
        on_file = await service.observations.existing_import_keys(current.patient_id, keys)
        seen: set[str] = set()
        for metric, key in zip(report.metrics, keys, strict=True):
            if key in seen or key in on_file:
                skipped += 1
                continue
            seen.add(key)
            # add_if_absent, not add: the on_file probe narrows the common case, but a
            # concurrent upload of the same report can slip between probe and write — the
            # DB partial-unique index makes the duplicate impossible and this skips it (#3).
            if await service.observations.add_if_absent(
                biomech_metric_to_observation(
                    metric,
                    kind=report.kind,
                    assessment_at=report.assessment_at,
                    condition=report.condition,
                    patient_id=current.patient_id,
                    import_key=key,
                )
            ):
                imported += 1
            else:
                skipped += 1

    # PHI write — one audit event, counts + report kind only (CLAUDE.md §5). Warnings
    # can carry parsed values, so only their COUNT is audited, never their text.
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="import_biomech",
            patient_id=current.patient_id,
            detail={
                "report_kind": report.kind.value if report.kind is not None else None,
                "imported": imported,
                "skipped": skipped,
                "warnings": len(warnings),
            },
        )
    )
    return BiomechImportOut(
        report_kind=report.kind.value if report.kind is not None else None,
        assessment_at=report.assessment_at,
        imported=imported,
        skipped=skipped,
        warnings=warnings,
    )
