"""Patient capture endpoints: the medication/supplement change log and between-visit
events/notes (ADR-0045 P2).

These ride the existing Observation model (no new tables) exactly like the other ingest
paths (routes/ingestion.py). Routes are thin: ownership comes from the authenticated
patient (never the body); the append-only mapping lives in app/ingestion; idempotency is
the shared `import_key` + add_if_absent invariant.

Postures (identical to the rest of the ingest surface):
- Patient role ONLY (`PatientUserDep` -> 403 clinician/ops, 401 anon).
- Capability-gated WRITES only: `ingest_medications` / `ingest_events` govern ingestion
  (409 when off). The GET list endpoints are NEVER gated — the toggle stops new capture,
  it must not block the patient's read of their own already-captured record (the same
  rows keep rendering in /me/visit-summary and /me/export regardless of the toggle).
- Every read is `Cache-Control: no-store` (the body is PHI).
- Every write/read emits ONE audit event — counts/refs only, never names/doses/note text.
- Appending to a medication_id the patient does not own is 404, never 403 (no existence leak).

NON-DIAGNOSTIC: this is a list/log the patient keeps — the app never adjusts, checks,
interacts, or recommends. No red-flag scanning of notes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import EmrServiceDep, PatientUserDep, require_capability
from app.ingestion.events import event_import_key, event_to_observation
from app.ingestion.medications import (
    fold_medications,
    medication_change_to_observation,
    medication_import_key,
    medication_register_to_observation,
    mint_medication_id,
)
from app.models.audit import AuditEvent
from app.models.observation import Observation, SourceType
from app.repositories.observation import ObservationRepository
from app.schemas.event import EventIn, EventList, EventOut
from app.schemas.medication import (
    MedicationChangeEntry,
    MedicationChangeIn,
    MedicationChangeOut,
    MedicationChangeType,
    MedicationLog,
    MedicationOut,
    MedicationRegisterIn,
)

router = APIRouter(tags=["medications"])


def _reject_future(day: date, *, now: datetime) -> None:
    """Reject a future date (422). The date is the patient's LOCAL calendar day, so accept
    up to UTC+14 — the furthest-ahead local date on Earth (mirrors the ADL check-in)."""
    if day > (now + timedelta(hours=14)).date():
        raise HTTPException(status_code=422, detail="date cannot be in the future")


async def _find_by_import_key(
    observations: ObservationRepository, patient_id: object, import_key: str, *, source: SourceType
) -> Observation | None:
    """The row already on file for an idempotent retry (same client_entry_id). Meds/events
    are low-volume, so the source-scoped read is cheap; a graceful skip returns the
    server-minted identity of the row that WON, never a fresh (uninserted) one."""
    assert isinstance(patient_id, object)  # patient_id is a uuid; typed loosely for the route
    rows = await observations.list_for_patient(patient_id, source=source)  # type: ignore[arg-type]
    return next((row for row in rows if row.import_key == import_key), None)


# --- Medications -----------------------------------------------------------------------


@router.post(
    "/medications",
    response_model=MedicationChangeOut,
    status_code=201,
    dependencies=[Depends(require_capability("ingest_medications"))],
)
async def register_medication(
    body: MedicationRegisterIn, current: PatientUserDep, service: EmrServiceDep
) -> MedicationChangeOut:
    """Register a NEW medication/supplement — mints the server-side `med:{uuid}` identity
    and writes the `added` change entry. Idempotent per client_entry_id: a retry of the
    same compose action is a graceful skip returning the existing medication's id."""
    assert current.patient_id is not None  # guaranteed by require_patient
    now = datetime.now(UTC)
    _reject_future(body.started_on, now=now)
    import_key = medication_import_key(body.client_entry_id)
    medication_id = mint_medication_id()
    row = medication_register_to_observation(
        body,
        patient_id=current.patient_id,
        medication_id=medication_id,
        import_key=import_key,
        recorded_at=now,
    )
    inserted = await service.observations.add_if_absent(row)
    if not inserted:
        # A retry of the same compose action: return the identity of the row that won,
        # not the freshly-minted (uninserted) one.
        existing = await _find_by_import_key(
            service.observations, current.patient_id, import_key, source=SourceType.medication
        )
        if existing is not None:
            medication_id = existing.code
            effective_at = existing.effective_at
        else:  # pragma: no cover - defensive: absent only under a concurrent delete
            effective_at = row.effective_at
    else:
        effective_at = row.effective_at
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="set_medication",
            patient_id=current.patient_id,
            detail={"kind": body.kind.value, "skipped": not inserted},
        )
    )
    return MedicationChangeOut(
        medication_id=medication_id,
        change_type=MedicationChangeType.added,
        effective_at=effective_at,
        skipped=not inserted,
    )


@router.post(
    "/medications/{medication_id}/changes",
    response_model=MedicationChangeOut,
    status_code=201,
    dependencies=[Depends(require_capability("ingest_medications"))],
)
async def append_medication_change(
    medication_id: str, body: MedicationChangeIn, current: PatientUserDep, service: EmrServiceDep
) -> MedicationChangeOut:
    """Append a `dose_changed` or `stopped` entry to an existing medication's log. 404 —
    never 403 — when the patient owns no medication with this id (no existence leak).
    Idempotent per client_entry_id."""
    assert current.patient_id is not None  # guaranteed by require_patient
    now = datetime.now(UTC)
    _reject_future(body.effective_date, now=now)
    existing_rows = await service.observations.list_for_patient(
        current.patient_id, code=medication_id, source=SourceType.medication
    )
    if not existing_rows:
        raise HTTPException(status_code=404, detail="No such medication")
    # Fold to carry the medication's display/kind/prescriber onto the new entry so it
    # folds and renders standalone (the change never mutates a prior row).
    folded = fold_medications(existing_rows)[0]
    import_key = medication_import_key(body.client_entry_id)
    row = medication_change_to_observation(
        body,
        patient_id=current.patient_id,
        medication_id=medication_id,
        display=folded.name,
        kind=folded.kind,
        prescriber=folded.prescriber,
        import_key=import_key,
        recorded_at=now,
    )
    inserted = await service.observations.add_if_absent(row)
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="record_medication_change",
            patient_id=current.patient_id,
            detail={"change_type": body.change_type.value, "skipped": not inserted},
        )
    )
    return MedicationChangeOut(
        medication_id=medication_id,
        change_type=body.change_type,
        effective_at=row.effective_at,
        skipped=not inserted,
    )


# Deliberately NO capability gate: ingest_medications governs the WRITE paths only
# (services/capability.py contract). Gating this read would let a clinician-managed or
# ops kill-switch toggle block the patient's access to their own already-captured
# record — a right-of-access inversion, while the same rows still render elsewhere.
@router.get("/medications", response_model=MedicationLog)
async def list_medications(
    current: PatientUserDep, service: EmrServiceDep, response: Response
) -> MedicationLog:
    """The patient's folded current medication list + per-med change log, active-first.
    Reads the FULL medication history (a med may predate any window). PHI: `no-store`."""
    assert current.patient_id is not None  # guaranteed by require_patient
    response.headers["Cache-Control"] = "no-store"
    rows = await service.observations.list_for_patient(
        current.patient_id, source=SourceType.medication
    )
    items = [
        MedicationOut(
            medication_id=folded.medication_id,
            name=folded.name,
            kind=folded.kind,
            status=folded.status,
            current_dose_amount=folded.current_dose_amount,
            current_dose_unit=folded.current_dose_unit,
            current_dose_text=folded.current_dose_text,
            prescriber=folded.prescriber,
            started_on=folded.started_on,
            last_change_at=folded.last_change_at,
            changes=[
                MedicationChangeEntry(
                    change_type=change.change_type,
                    effective_at=change.effective_at,
                    dose_amount=change.dose_amount,
                    dose_unit=change.dose_unit,
                    dose_text=change.dose_text,
                    reason=change.reason,
                )
                for change in folded.changes
            ],
        )
        for folded in fold_medications(rows)
    ]
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_medications",
            patient_id=current.patient_id,
            detail={"medications": len(items), "rows": len(rows)},
        )
    )
    return MedicationLog(items=items)


# --- Events / notes --------------------------------------------------------------------


@router.post(
    "/events",
    response_model=EventOut,
    status_code=201,
    dependencies=[Depends(require_capability("ingest_events"))],
)
async def record_event(body: EventIn, current: PatientUserDep, service: EmrServiceDep) -> EventOut:
    """Record one between-visit event/note as an append-only row. Idempotent per
    client_entry_id: two genuine same-day falls (distinct ids) both persist; a retry of one
    compose action skips. No red-flag scanning/triage."""
    assert current.patient_id is not None  # guaranteed by require_patient
    now = datetime.now(UTC)
    _reject_future(body.effective_date, now=now)
    import_key = event_import_key(body.client_entry_id)
    row = event_to_observation(
        body, patient_id=current.patient_id, import_key=import_key, recorded_at=now
    )
    inserted = await service.observations.add_if_absent(row)
    event_id = row.id
    if not inserted:
        existing = await _find_by_import_key(
            service.observations, current.patient_id, import_key, source=SourceType.event
        )
        if existing is not None and existing.id is not None:
            event_id = existing.id
    assert event_id is not None  # add_if_absent mints the id on insert; skip resolves above
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="record_event",
            patient_id=current.patient_id,
            detail={"type": body.type.value, "skipped": not inserted},
        )
    )
    return EventOut(
        event_id=event_id,
        type=body.type,
        effective_at=row.effective_at,
        note=body.note,
        reviewed=False,
        skipped=not inserted,
    )


# Deliberately NO capability gate — same read-path posture as GET /medications above.
@router.get("/events", response_model=EventList)
async def list_events(
    current: PatientUserDep, service: EmrServiceDep, response: Response
) -> EventList:
    """The patient's between-visit events & notes, newest-first. PHI: `no-store`."""
    assert current.patient_id is not None  # guaranteed by require_patient
    response.headers["Cache-Control"] = "no-store"
    rows = await service.observations.list_for_patient(
        current.patient_id, source=SourceType.event, newest_first=True
    )
    items: list[EventOut] = []
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        assert row.id is not None  # persisted rows always carry an id
        items.append(
            EventOut(
                event_id=row.id,
                type=str(payload.get("type") or "note"),
                effective_at=row.effective_at,
                note=row.value_text,
                reviewed=bool(payload.get("reviewed", False)),
                skipped=False,
            )
        )
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_events",
            patient_id=current.patient_id,
            detail={"events": len(items)},
        )
    )
    return EventList(items=items)
