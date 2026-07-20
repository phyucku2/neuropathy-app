"""Unit tests for the medication change-log mapping + fold (ADR-0045 P2).

Pure mapping only — no client, no DB, no wall clock (times threaded in). All data
synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from app.ingestion.medications import (
    MEDICATION_CODE_SYSTEM,
    fold_medications,
    medication_change_to_observation,
    medication_import_key,
    medication_register_to_observation,
    mint_medication_id,
)
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.schemas.medication import (
    MedicationChangeIn,
    MedicationChangeType,
    MedicationKind,
    MedicationRegisterIn,
    MedicationStatus,
)

PATIENT_ID = uuid4()
NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _register(
    *,
    name: str = "Gabapentin",
    kind: MedicationKind = MedicationKind.prescription,
    dose_amount: float | None = 300.0,
    dose_unit: str | None = "mg",
    dose_text: str | None = None,
    prescriber: str | None = "Dr Synthetic",
    reason: str | None = "nerve pain",
    started_on: date = date(2026, 5, 1),
) -> MedicationRegisterIn:
    return MedicationRegisterIn(
        name=name,
        kind=kind,
        dose_amount=dose_amount,
        dose_unit=dose_unit,
        dose_text=dose_text,
        prescriber=prescriber,
        reason=reason,
        started_on=started_on,
        client_entry_id=uuid4(),
    )


def _change(
    *,
    change_type: MedicationChangeType = MedicationChangeType.dose_changed,
    dose_amount: float | None = 600.0,
    dose_unit: str | None = "mg",
    dose_text: str | None = None,
    reason: str | None = None,
    effective_date: date = date(2026, 6, 15),
) -> MedicationChangeIn:
    return MedicationChangeIn(
        change_type=change_type,
        dose_amount=dose_amount,
        dose_unit=dose_unit,
        dose_text=dose_text,
        reason=reason,
        effective_date=effective_date,
        client_entry_id=uuid4(),
    )


# --- append-only row mapping -----------------------------------------------------------


def test_register_maps_to_append_only_added_row() -> None:
    med_id = mint_medication_id()
    assert med_id.startswith("med:")
    row = medication_register_to_observation(
        _register(),
        patient_id=PATIENT_ID,
        medication_id=med_id,
        import_key=medication_import_key(uuid4()),
        recorded_at=NOW,
    )
    assert row.source is SourceType.medication
    assert row.origin is DataOrigin.patient_reported
    assert row.status is ObservationStatus.final
    assert row.revises_id is None  # append-only — never supersedes
    assert row.recorded_by_role == "patient"
    assert row.code == med_id
    assert row.code_system == MEDICATION_CODE_SYSTEM
    assert row.value_text == "Gabapentin"  # display name
    assert row.value_num == 300.0
    assert row.unit == "mg"
    assert row.effective_at == datetime(2026, 5, 1, tzinfo=UTC)  # the change date
    assert row.recorded_at == NOW
    assert row.payload["change_type"] == MedicationChangeType.added.value
    assert row.payload["kind"] == "prescription"
    assert row.payload["prescriber"] == "Dr Synthetic"
    assert row.quality == {"human_confirmed": True, "source_mode": "manual"}


def test_dose_change_and_stop_map_to_append_only_rows() -> None:
    med_id = mint_medication_id()
    changed = medication_change_to_observation(
        _change(change_type=MedicationChangeType.dose_changed, dose_amount=600.0),
        patient_id=PATIENT_ID,
        medication_id=med_id,
        display="Gabapentin",
        kind="prescription",
        prescriber="Dr Synthetic",
        import_key=medication_import_key(uuid4()),
        recorded_at=NOW,
    )
    assert changed.revises_id is None  # a dose change is HISTORY, never a correction
    assert changed.code == med_id  # shares the medication identity
    assert changed.value_num == 600.0
    assert changed.payload["change_type"] == "dose_changed"

    stopped = medication_change_to_observation(
        _change(change_type=MedicationChangeType.stopped, dose_amount=None, dose_unit=None),
        patient_id=PATIENT_ID,
        medication_id=med_id,
        display="Gabapentin",
        kind="prescription",
        prescriber="Dr Synthetic",
        import_key=medication_import_key(uuid4()),
        recorded_at=NOW,
    )
    assert stopped.revises_id is None
    assert stopped.payload["change_type"] == "stopped"


def test_import_key_folds_the_client_entry_id() -> None:
    cid = uuid4()
    assert medication_import_key(cid) == f"medication:{cid}"


# --- fold ------------------------------------------------------------------------------


def _row(
    med_id: str,
    *,
    change_type: str,
    dose_amount: float | None,
    effective_day: int,
    recorded_day: int | None = None,
    name: str = "Gabapentin",
    kind: str = "prescription",
    prescriber: str | None = "Dr Synthetic",
    dose_unit: str | None = "mg",
) -> Observation:
    eff = datetime(2026, effective_day // 30 + 1, effective_day % 30 + 1, tzinfo=UTC)
    rec = eff if recorded_day is None else datetime(2026, 6, recorded_day, tzinfo=UTC)
    return Observation(
        id=uuid4(),
        patient_id=PATIENT_ID,
        source=SourceType.medication,
        origin=DataOrigin.patient_reported,
        code=med_id,
        code_system=MEDICATION_CODE_SYSTEM,
        value_num=dose_amount,
        value_text=name,
        unit=dose_unit,
        effective_at=eff,
        recorded_at=rec,
        status=ObservationStatus.final,
        quality={"human_confirmed": True, "source_mode": "manual"},
        payload={
            "change_type": change_type,
            "kind": kind,
            "prescriber": prescriber,
            "dose_text": None,
        },
    )


def test_fold_latest_change_type_and_latest_dose_win() -> None:
    med_id = "med:aaa"
    rows = [
        _row(med_id, change_type="added", dose_amount=300.0, effective_day=1),
        _row(med_id, change_type="dose_changed", dose_amount=600.0, effective_day=40),
    ]
    folded = fold_medications(rows)
    assert len(folded) == 1
    med = folded[0]
    assert med.status == MedicationStatus.active.value
    assert med.current_dose_amount == 600.0  # latest dose wins
    assert med.started_on == date(2026, 1, 2)  # earliest effective_at
    assert len(med.changes) == 2


def test_fold_stopped_med_still_appears_and_keeps_last_dose() -> None:
    med_id = "med:bbb"
    rows = [
        _row(med_id, change_type="added", dose_amount=300.0, effective_day=1),
        _row(med_id, change_type="dose_changed", dose_amount=600.0, effective_day=40),
        _row(med_id, change_type="stopped", dose_amount=None, effective_day=70, dose_unit=None),
    ]
    med = fold_medications(rows)[0]
    assert med.status == MedicationStatus.stopped.value  # latest change_type
    assert med.current_dose_amount == 600.0  # a stopped entry without a dose keeps the last


def test_fold_tie_broken_by_recorded_at() -> None:
    med_id = "med:ccc"
    # Two entries with the SAME effective_at; the later recorded_at is the current state.
    rows = [
        _row(med_id, change_type="added", dose_amount=300.0, effective_day=40, recorded_day=1),
        _row(
            med_id, change_type="dose_changed", dose_amount=900.0, effective_day=40, recorded_day=5
        ),
    ]
    med = fold_medications(rows)[0]
    assert med.current_dose_amount == 900.0


def test_fold_groups_multiple_meds_by_code_active_first() -> None:
    stopped = [
        _row("med:zzz", change_type="added", dose_amount=10.0, effective_day=1, name="Aspirin"),
        _row("med:zzz", change_type="stopped", dose_amount=None, effective_day=5, name="Aspirin"),
    ]
    active = [
        _row("med:aaa", change_type="added", dose_amount=300.0, effective_day=1, name="Gabapentin"),
    ]
    folded = fold_medications(stopped + active)
    # Active-first, then by name — the stopped Aspirin sorts after the active Gabapentin.
    assert [m.name for m in folded] == ["Gabapentin", "Aspirin"]
    assert [m.status for m in folded] == [
        MedicationStatus.active.value,
        MedicationStatus.stopped.value,
    ]


def test_fold_ignores_non_medication_rows() -> None:
    med = _row("med:aaa", change_type="added", dose_amount=300.0, effective_day=1)
    other = Observation(
        id=uuid4(),
        patient_id=PATIENT_ID,
        source=SourceType.event,
        origin=DataOrigin.patient_reported,
        code="event_fall",
        effective_at=NOW,
        recorded_at=NOW,
        status=ObservationStatus.final,
        quality={},
        payload={},
    )
    assert len(fold_medications([med, other])) == 1
