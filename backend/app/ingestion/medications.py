"""Medication & supplement change-log ingestion — append-only Observation rows (ADR-0045 P2).

A pure mapping module like ingestion/adl.py and ingestion/wearable.py: it builds rows and
folds them, with NO repository, network, or wall clock (times are threaded in). Every entry
is its OWN append-only row (`revises_id=None`) — `added`/`dose_changed`/`stopped` never
supersede one another, so the full non-superseded set for a medication's `code` IS its
change history. Current state is a pure fold of that set, oldest→newest.

`revises_id` stays reserved for correcting a mistaken entry (the existing correction
pattern, ADR-0006) — a dose change is history, never a correction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time

from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.schemas.medication import (
    MedicationChangeIn,
    MedicationChangeType,
    MedicationRegisterIn,
    MedicationStatus,
)

# The stable per-medication code system: every change entry for one drug shares its
# server-minted `med:{uuid4}` identity so they group via ix_observation_patient_code_time.
MEDICATION_CODE_SYSTEM = "neuropathy-app/medication"


def mint_medication_id() -> str:
    """Server-minted stable identity shared by every change entry for one medication."""
    return f"med:{uuid.uuid4()}"


def medication_import_key(client_entry_id: uuid.UUID) -> str:
    """Fold the client-minted entry id into the import key (ALCOA sweep #3): a network
    retry of one compose action is a graceful add_if_absent skip; two genuine changes
    (distinct ids) both persist."""
    return f"{SourceType.medication.value}:{client_entry_id}"


def _date_to_datetime(day: date) -> datetime:
    """The change date as a tz-aware UTC datetime at day-start (effective_at)."""
    return datetime.combine(day, time.min, tzinfo=UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def medication_register_to_observation(
    body: MedicationRegisterIn,
    *,
    patient_id: uuid.UUID,
    medication_id: str,
    import_key: str,
    recorded_at: datetime,
) -> Observation:
    """The `added` entry minted at registration — the first row of a medication's log."""
    return Observation(
        patient_id=patient_id,
        source=SourceType.medication,
        origin=DataOrigin.patient_reported,
        code=medication_id,
        code_system=MEDICATION_CODE_SYSTEM,
        value_num=body.dose_amount,
        value_text=body.name,
        unit=body.dose_unit,
        effective_at=_date_to_datetime(body.started_on),
        recorded_at=recorded_at,
        status=ObservationStatus.final,
        revises_id=None,
        recorded_by_role="patient",
        import_key=import_key,
        quality={"human_confirmed": True, "source_mode": "manual"},
        payload={
            "change_type": MedicationChangeType.added.value,
            "kind": body.kind.value,
            "dose_text": body.dose_text,
            "prescriber": body.prescriber,
            "reason": body.reason,
            "display": body.name,
        },
    )


def medication_change_to_observation(
    body: MedicationChangeIn,
    *,
    patient_id: uuid.UUID,
    medication_id: str,
    display: str,
    kind: str,
    prescriber: str | None,
    import_key: str,
    recorded_at: datetime,
) -> Observation:
    """A `dose_changed` or `stopped` entry appended to an existing medication's log.

    `display`/`kind`/`prescriber` carry forward from the medication's existing entries so
    the row folds and renders standalone; the change never mutates a prior row.
    """
    return Observation(
        patient_id=patient_id,
        source=SourceType.medication,
        origin=DataOrigin.patient_reported,
        code=medication_id,
        code_system=MEDICATION_CODE_SYSTEM,
        value_num=body.dose_amount,
        value_text=display,
        unit=body.dose_unit,
        effective_at=_date_to_datetime(body.effective_date),
        recorded_at=recorded_at,
        status=ObservationStatus.final,
        revises_id=None,
        recorded_by_role="patient",
        import_key=import_key,
        quality={"human_confirmed": True, "source_mode": "manual"},
        payload={
            "change_type": body.change_type.value,
            "kind": kind,
            "dose_text": body.dose_text,
            "prescriber": prescriber,
            "reason": body.reason,
            "display": display,
        },
    )


@dataclass(frozen=True)
class MedicationChangeRecord:
    """One entry in a medication's append-only log (a projection of one Observation row)."""

    change_type: str
    effective_at: datetime
    dose_amount: float | None
    dose_unit: str | None
    dose_text: str | None
    reason: str | None
    recorded_at: datetime


@dataclass(frozen=True)
class FoldedMedication:
    """A medication folded to its current state, plus its full change log."""

    medication_id: str
    name: str
    kind: str
    status: str
    current_dose_amount: float | None
    current_dose_unit: str | None
    current_dose_text: str | None
    prescriber: str | None
    started_on: date
    last_change_at: datetime
    changes: list[MedicationChangeRecord] = field(default_factory=list)


def _payload_str(payload: object, key: str) -> str | None:
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return None


def _to_change_record(row: Observation) -> MedicationChangeRecord:
    return MedicationChangeRecord(
        change_type=_payload_str(row.payload, "change_type") or MedicationChangeType.added.value,
        effective_at=_aware(row.effective_at),
        dose_amount=row.value_num,
        dose_unit=row.unit,
        dose_text=_payload_str(row.payload, "dose_text"),
        reason=_payload_str(row.payload, "reason"),
        recorded_at=_aware(row.recorded_at),
    )


def _fold_one(medication_id: str, rows: list[Observation]) -> FoldedMedication:
    # Oldest→newest by effective_at, ties broken by recorded_at (deterministic fold).
    ordered = sorted(rows, key=lambda r: (_aware(r.effective_at), _aware(r.recorded_at)))
    changes = [_to_change_record(row) for row in ordered]
    latest = changes[-1]
    earliest = changes[0]

    # Latest change_type sets active/stopped; a stopped med still renders (never dropped).
    status = (
        MedicationStatus.stopped.value
        if latest.change_type == MedicationChangeType.stopped.value
        else MedicationStatus.active.value
    )

    # Latest dose wins: the most recent entry that actually carried a dose (a `stopped`
    # entry with no dose does not erase the last known dose).
    dose_amount: float | None = None
    dose_unit: str | None = None
    dose_text: str | None = None
    for change in changes:
        if change.dose_amount is not None or change.dose_unit is not None or change.dose_text:
            dose_amount, dose_unit, dose_text = (
                change.dose_amount,
                change.dose_unit,
                change.dose_text,
            )

    # Name/kind/prescriber: the latest entry that carries each (all rows carry name+kind;
    # prescriber may be absent on later entries, so keep the most recent non-null).
    name = next(
        (r.value_text for r in reversed(ordered) if r.value_text), ordered[-1].value_text or ""
    )
    kind = next(
        (
            _payload_str(r.payload, "kind")
            for r in reversed(ordered)
            if _payload_str(r.payload, "kind")
        ),
        "",
    )
    prescriber = next(
        (
            _payload_str(r.payload, "prescriber")
            for r in reversed(ordered)
            if _payload_str(r.payload, "prescriber")
        ),
        None,
    )

    return FoldedMedication(
        medication_id=medication_id,
        name=name or "",
        kind=kind or "",
        status=status,
        current_dose_amount=dose_amount,
        current_dose_unit=dose_unit,
        current_dose_text=dose_text,
        prescriber=prescriber,
        started_on=earliest.effective_at.date(),
        last_change_at=latest.effective_at,
        changes=changes,
    )


def fold_medications(rows: list[Observation]) -> list[FoldedMedication]:
    """Fold medication Observation rows to per-medication current states, active-first.

    Groups by `code` (the medication identity), folds each group oldest→newest, and sorts
    active medications before stopped ones, then by name (a stopped med still appears).
    Rows of other sources are ignored (defense in depth — callers pass a scoped read).
    """
    grouped: dict[str, list[Observation]] = {}
    for row in rows:
        if row.source is not SourceType.medication:
            continue
        grouped.setdefault(row.code, []).append(row)
    folded = [_fold_one(code, group) for code, group in grouped.items()]
    folded.sort(key=lambda m: (m.status != MedicationStatus.active.value, m.name.lower()))
    return folded
