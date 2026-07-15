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
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    CapabilityServiceDep,
    EmrServiceDep,
    PatientUserDep,
    require_capability,
)
from app.ingestion.adl import (
    ADL_CODES,
    SYMPTOM_CODES,
    adl_check_in_to_observations,
    day_bounds_utc,
    symptom_check_in_to_observations,
)
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
from app.schemas.lab import LabStatus

router = APIRouter(tags=["ingestion"])


# The capability gates are the enforcement seam's first two consumers (ADR-0013):
# server-side toggles refuse the write with 409 when the feature is off; absence of a
# toggle row means the registry default, so untouched accounts behave exactly as before.
@router.post(
    "/labs",
    response_model=LabImportOut,
    dependencies=[Depends(require_capability("ingest_labs"))],
)
async def import_labs(
    body: LabImportIn, current: PatientUserDep, service: EmrServiceDep
) -> LabImportOut:
    """Import a panel of on-device-confirmed lab results as research-grade rows.

    Idempotent: each result is keyed by its content identity, so re-posting the same
    panel (a retry, a re-scan of the same report) skips rows already on file.
    """
    assert current.patient_id is not None  # guaranteed by require_patient
    # This endpoint receives values the patient has ALREADY confirmed on-device: only
    # final results are accepted. Anything else (preliminary, entered_in_error) would
    # enter the record branded human-confirmed and consume its idempotency key,
    # permanently blocking the real value (review finding, verified live).
    if any(result.status is not LabStatus.final for result in body.results):
        raise HTTPException(
            status_code=422,
            detail="Only confirmed (status=final) results may be uploaded",
        )
    keys = [lab_import_key(result) for result in body.results]
    # ONE existence probe for the whole batch (indexed column), not N queries.
    on_file = await service.observations.existing_import_keys(current.patient_id, keys)
    imported = 0
    skipped = 0
    seen: set[str] = set()
    for result, key in zip(body.results, keys, strict=True):
        if key in seen or key in on_file:
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
    codes: Iterable[str],
) -> dict[str, uuid.UUID]:
    """The current (non-superseded, analyzable) row ids for one calendar day, per code.

    These are the rows a re-submitted check-in supersedes. The repository already
    resolves revises_id chains to the current record, so a third submission chains
    onto the second, never back onto the first.
    """
    revises: dict[str, uuid.UUID] = {}
    for code in codes:
        rows = await observations.list_for_patient(patient_id, code=code, since=start)
        same_day = [r for r in rows if _aware(r.effective_at) < end]
        if same_day and same_day[-1].id is not None:
            revises[code] = same_day[-1].id
    return revises


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@router.post(
    "/adl",
    response_model=AdlCheckInOut,
    dependencies=[Depends(require_capability("ingest_adl"))],
)
async def record_adl_check_in(
    body: AdlCheckInIn,
    current: PatientUserDep,
    service: EmrServiceDep,
    capabilities: CapabilityServiceDep,
) -> AdlCheckInOut:
    """Record the daily function check-in: three 0-4 answers plus the derived 0-12
    composite. One check-in per calendar day — a second POST for the same date
    supersedes the first via revises_id chains (ADR-0006), never an overwrite.

    When the `ingest_symptoms` capability is on for this patient (ADR-0034 Phase 1),
    the optional 0-10 pain + numbness items are ALSO persisted as their own higher-is-
    worse observations. When it is off, those answers are ignored entirely — a stored
    "off" the code actually respects (enforced-flag honesty, ADR-0013), so nothing is
    captured regardless of what the client sends."""
    assert current.patient_id is not None  # guaranteed by require_patient
    now = datetime.now(UTC)
    day = body.check_in_date or now.date()
    # check_in_date is the patient's LOCAL calendar day; a UTC-based "future" check
    # would reject valid mornings west of the date line (review finding). Accept up
    # to UTC+14 — the furthest-ahead local date on Earth.
    if day > (now + timedelta(hours=14)).date():
        raise HTTPException(status_code=422, detail="check_in_date cannot be in the future")

    # The symptom sub-feature is a SEPARATE, opt-in toggle from the base check-in
    # (which the endpoint's require_capability("ingest_adl") gate already enforced).
    symptoms_on = await capabilities.is_active(current.patient_id, "ingest_symptoms", now=now)

    start, end = day_bounds_utc(day)
    # Only resolve symptom supersessions when the feature is on AND an item was answered.
    codes = list(ADL_CODES)
    if symptoms_on and (body.pain is not None or body.numbness is not None):
        codes += list(SYMPTOM_CODES)
    revises = await _current_same_day_rows(
        service.observations, current.patient_id, start, end, codes
    )
    rows = adl_check_in_to_observations(
        body, patient_id=current.patient_id, effective_at=start, revises=revises
    )
    if symptoms_on:
        rows += symptom_check_in_to_observations(
            body, patient_id=current.patient_id, effective_at=start, revises=revises
        )
    for row in rows:
        await service.observations.add(row)
    # PHI write — audit-logged with counts/flags only, never answer values (CLAUDE.md §5).
    symptom_rows = sum(1 for row in rows if row.code in SYMPTOM_CODES)
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="record_adl",
            patient_id=current.patient_id,
            detail={
                "observations": len(rows),
                "superseded": len(revises),
                "symptoms": symptom_rows,
            },
        )
    )
    return AdlCheckInOut(
        check_in_date=day,
        daily_score=body.walking + body.stairs + body.balance_confidence,
        superseded=bool(revises),
    )


def observation_to_item(row: Observation) -> ObservationItem:
    """Display-safe projection of an analyzable record — shared with the clinician
    observations view (routes/clinic.py) so both surfaces expose identical fields."""
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
    # Pagination is pushed into storage (LIMIT/OFFSET + count) so a 50-row page never
    # materializes a multi-year history (review finding; standards.md read budget).
    page = await service.observations.list_for_patient(
        current.patient_id, code=code, limit=limit, offset=offset, newest_first=True
    )
    total = await service.observations.count_for_patient(current.patient_id, code=code)
    # PHI read — audit-logged like every other health-data access, counts only.
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_observations",
            patient_id=current.patient_id,
            detail={"returned": len(page), "total": total},
        )
    )
    return ObservationPage(
        items=[observation_to_item(row) for row in page], total=total, limit=limit, offset=offset
    )
