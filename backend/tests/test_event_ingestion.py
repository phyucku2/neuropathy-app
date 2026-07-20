"""Unit tests for the between-visit event/note mapping (ADR-0045 P2).

Pure mapping only. All data synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.ingestion.events import EVENT_CODES, event_import_key, event_to_observation
from app.models.observation import DataOrigin, ObservationStatus, SourceType
from app.schemas.event import EventIn, EventType

PATIENT_ID = uuid4()
NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _event(
    *, type: EventType = EventType.fall, note: str | None = None, day: date = date(2026, 7, 10)
) -> EventIn:
    return EventIn(type=type, effective_date=day, note=note, client_entry_id=uuid4())


@pytest.mark.parametrize(
    ("event_type", "expected_code"),
    [
        (EventType.fall, "event_fall"),
        (EventType.er_visit, "event_er_visit"),
        (EventType.new_provider, "event_new_provider"),
        (EventType.hospitalization, "event_hospitalization"),
        (EventType.new_supplement, "event_new_supplement"),
        (EventType.note, "patient_note"),
    ],
)
def test_each_type_maps_to_its_code(event_type: EventType, expected_code: str) -> None:
    note = "some words" if event_type is EventType.note else None
    row = event_to_observation(
        _event(type=event_type, note=note),
        patient_id=PATIENT_ID,
        import_key=event_import_key(uuid4()),
        recorded_at=NOW,
    )
    assert row.source is SourceType.event
    assert row.origin is DataOrigin.patient_reported
    assert row.status is ObservationStatus.final
    assert row.revises_id is None  # append-only
    assert row.recorded_by_role == "patient"
    assert row.code == expected_code
    assert row.effective_at == datetime(2026, 7, 10, tzinfo=UTC)
    assert row.payload["type"] == event_type.value
    assert row.payload["reviewed"] is False
    assert row.quality == {"human_confirmed": True}


def test_note_lands_verbatim_in_value_text() -> None:
    row = event_to_observation(
        _event(type=EventType.fall, note="Fell in the kitchen"),
        patient_id=PATIENT_ID,
        import_key=event_import_key(uuid4()),
        recorded_at=NOW,
    )
    assert row.value_text == "Fell in the kitchen"
    assert row.value_num is None


def test_import_key_folds_the_client_entry_id() -> None:
    cid = uuid4()
    assert event_import_key(cid) == f"event:{cid}"


def test_vocabulary_covers_every_event_type() -> None:
    assert set(EVENT_CODES) == set(EventType)
