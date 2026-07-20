"""Schema-boundary validation for the medication + event capture surface (ADR-0045 P2).

The route maps a ValidationError to 422; these pin the boundary rules directly. All data
synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.event import EVENT_NOTE_MAX, EventIn, EventType
from app.schemas.medication import (
    MedicationChangeIn,
    MedicationChangeType,
    MedicationRegisterIn,
)


def test_dose_changed_with_no_dose_fields_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one of"):
        MedicationChangeIn(
            change_type=MedicationChangeType.dose_changed,
            effective_date=date(2026, 6, 1),
            client_entry_id=uuid4(),
        )


def test_dose_changed_with_only_dose_text_is_accepted() -> None:
    change = MedicationChangeIn(
        change_type=MedicationChangeType.dose_changed,
        dose_text="two tablets",
        effective_date=date(2026, 6, 1),
        client_entry_id=uuid4(),
    )
    assert change.dose_text == "two tablets"


def test_stopped_needs_no_dose() -> None:
    change = MedicationChangeIn(
        change_type=MedicationChangeType.stopped,
        effective_date=date(2026, 6, 1),
        client_entry_id=uuid4(),
    )
    assert change.change_type is MedicationChangeType.stopped


def test_added_via_change_schema_is_rejected() -> None:
    with pytest.raises(ValidationError, match="POST /medications"):
        MedicationChangeIn(
            change_type=MedicationChangeType.added,
            dose_amount=1.0,
            effective_date=date(2026, 6, 1),
            client_entry_id=uuid4(),
        )


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MedicationRegisterIn(
            name="Gabapentin",
            kind="herbal",  # type: ignore[arg-type]
            started_on=date(2026, 6, 1),
            client_entry_id=uuid4(),
        )


def test_name_over_200_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MedicationRegisterIn(
            name="x" * 201,
            kind="supplement",  # type: ignore[arg-type]
            started_on=date(2026, 6, 1),
            client_entry_id=uuid4(),
        )


def test_note_event_without_note_is_rejected() -> None:
    with pytest.raises(ValidationError, match="non-empty note"):
        EventIn(type=EventType.note, effective_date=date(2026, 6, 1), client_entry_id=uuid4())


def test_note_event_with_whitespace_only_note_is_rejected() -> None:
    with pytest.raises(ValidationError, match="non-empty note"):
        EventIn(
            type=EventType.note,
            note="   ",
            effective_date=date(2026, 6, 1),
            client_entry_id=uuid4(),
        )


def test_note_over_cap_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EventIn(
            type=EventType.fall,
            note="x" * (EVENT_NOTE_MAX + 1),
            effective_date=date(2026, 6, 1),
            client_entry_id=uuid4(),
        )


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EventIn(
            type="earthquake",  # type: ignore[arg-type]
            effective_date=date(2026, 6, 1),
            client_entry_id=uuid4(),
        )
