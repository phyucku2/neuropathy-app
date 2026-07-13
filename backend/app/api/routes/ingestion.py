"""Patient data-entry endpoints: lab upload, ADL daily check-in, observations list.

These complete the ingest surface next to the EMR pull (ADR-0003). Routes are thin:
ownership comes from the authenticated patient (never from the body), mapping lives in
app/ingestion, storage behind the repositories on EmrServiceDep (the process-wide home
of the shared stores until DB wiring lands — see deps._default_emr_service).

Contracts:
- POST /labs receives structured values the patient already confirmed on-device (the
  app OCRs + human-confirms locally, ADR-0003). Idempotent per content identity.
- POST /adl records one check-in per calendar day; a re-submission for the same day
  supersedes the first via revises_id chains (ADR-0006), never an overwrite.
- GET /observations paginates by limit (1-100, default 50) + offset, newest first by
  effective_at, optional exact `code` filter.
- Every PHI read/write here is audit-logged with counts only, never values.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import EmrServiceDep, PatientUserDep
from app.ingestion.adl import ADL_CODES, adl_check_in_to_observations, day_bounds_utc
from app.ingestion.labs import lab_import_key, lab_result_to_observation
from app.models.audit import AuditEvent
from app.models.observation import DataOrigin, Observation
from app.repositories.observation import ObservationRepository
from app.schemas.ingestion import (
    AdlCheckInIn,
    AdlCheckInOut,
    LabImportIn,
    LabImportOut,
    ObservationItem,
    ObservationPage,
)

router = APIRouter(tags=["ingestion"])


@router.post("/labs", response_model=LabImportOut)
async def import_labs(
    body: LabImportIn, current: PatientUserDep, service: EmrServiceDep
) -> LabImportOut:
    """Import a panel of on-device-confirmed lab results as research-grade rows.

    Idempotent: each result is keyed by its content identity, so re-posting the same
    panel (a retry, a re-scan of the same report) skips rows already on file.
    """
    assert current.patient_id is not None  # guaranteed by require_patient
    imported = 0
    skipped = 0
    seen: set[str] = set()
    for result in body.results:
        key = lab_import_key(result)
        if key in seen or await service.observations.has_import_key(current.patient_id, key):
            skipped += 1
            continue
        seen.add(key)
        await service.observations.add(
            lab_result_to_observation(
                result,
                patient_id=current.patient_id,
                origin=DataOrigin.document_imported,
                recorded_by_role="patient",
                # The mobile app's human-confirm step is what makes these values
                # trustworthy (ADR-0003 / data-standards quality contract).
                quality={"human_confirmed": True},
                import_key=key,
            )
        )
        imported += 1
    # PHI write — one audit event for the batch, counts only (CLAUDE.md §5).
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="import_labs",
            patient_id=current.patient_id,
            detail={
                "origin": DataOrigin.document_imported.value,
                "received": len(body.results),
                "imported": imported,
                "skipped": skipped,
            },
        )
    )
    return LabImportOut(imported=imported, skipped=skipped)


async def _current_same_day_rows(
    observations: ObservationRepository,
    patient_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> dict[str, uuid.UUID]:
    """The current (non-superseded, analyzable) ADL row ids for one calendar day.

    These are the rows a re-submitted check-in supersedes. The repository already
    resolves revises_id chains to the current record, so a third submission chains
    onto the second, never back onto the first.
    """
    revises: dict[str, uuid.UUID] = {}
    for code in ADL_CODES:
        rows = await observations.list_for_patient(patient_id, code=code, since=start)
        same_day = [r for r in rows if _aware(r.effective_at) < end]
        if same_day and same_day[-1].id is not None:
            revises[code] = same_day[-1].id
    return revises


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@router.post("/adl", response_model=AdlCheckInOut)
async def record_adl_check_in(
    body: AdlCheckInIn, current: PatientUserDep, service: EmrServiceDep
) -> AdlCheckInOut:
    """Record the daily function check-in: three 0-4 answers plus the derived 0-12
    composite. One check-in per calendar day — a second POST for the same date
    supersedes the first via revises_id chains (ADR-0006), never an overwrite."""
    assert current.patient_id is not None  # guaranteed by require_patient
    now = datetime.now(UTC)
    day = body.check_in_date or now.date()
    if day > now.date():
        raise HTTPException(status_code=422, detail="check_in_date cannot be in the future")

    start, end = day_bounds_utc(day)
    revises = await _current_same_day_rows(service.observations, current.patient_id, start, end)
    rows = adl_check_in_to_observations(
        body, patient_id=current.patient_id, effective_at=start, revises=revises
    )
    for row in rows:
        await service.observations.add(row)
    # PHI write — audit-logged with counts only, never answer values (CLAUDE.md §5).
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="record_adl",
            patient_id=current.patient_id,
            detail={"observations": len(rows), "superseded": len(revises)},
        )
    )
    return AdlCheckInOut(
        check_in_date=day,
        daily_score=body.walking + body.stairs + body.balance_confidence,
        superseded=bool(revises),
    )


def _to_item(row: Observation) -> ObservationItem:
    display = row.payload.get("display") if isinstance(row.payload, dict) else None
    return ObservationItem(
        code=row.code,
        display=display if isinstance(display, str) else None,
        value=row.value_num,
        value_text=row.value_text,
        unit=row.unit,
        effective_at=row.effective_at,
        source=row.source.value,
        status=row.status.value,
    )


@router.get("/observations", response_model=ObservationPage)
async def list_observations(
    current: PatientUserDep,
    service: EmrServiceDep,
    code: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ObservationPage:
    """The patient's own analyzable records (superseded and errored rows excluded),
    newest first for display. Offset-paginated: limit 1-100 (default 50), offset >= 0;
    optional exact `code` filter (e.g. "4548-4" or "adl_daily_score")."""
    assert current.patient_id is not None  # guaranteed by require_patient
    rows = await service.observations.list_for_patient(current.patient_id, code=code)
    rows.reverse()  # repository returns oldest first; display wants newest first
    page = rows[offset : offset + limit]
    # PHI read — audit-logged like every other health-data access, counts only.
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_observations",
            patient_id=current.patient_id,
            detail={"returned": len(page), "total": len(rows)},
        )
    )
    return ObservationPage(
        items=[_to_item(row) for row in page], total=len(rows), limit=limit, offset=offset
    )
