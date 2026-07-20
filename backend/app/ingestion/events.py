"""Between-visit event/note ingestion — append-only Observation rows (ADR-0045 P2).

A pure mapping module (mirrors ingestion/adl.py): one Observation row per event, no
repository or wall clock. Free-text (`value_text`) is the patient's own words — PHI, never
fed to AI narration. A closed EVENT_CODES vocabulary maps each event type to a stable code
and a plain-language display.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.schemas.event import EventIn, EventType

# The closed vocabulary: type -> (stable code, plain-language display). `note` gets the
# generic `patient_note` code (a free-text note, not a categorized event).
EVENT_CODES: dict[EventType, tuple[str, str]] = {
    EventType.fall: ("event_fall", "Fall"),
    EventType.er_visit: ("event_er_visit", "ER visit"),
    EventType.new_provider: ("event_new_provider", "New provider"),
    EventType.hospitalization: ("event_hospitalization", "Hospitalization"),
    EventType.new_supplement: ("event_new_supplement", "New supplement"),
    EventType.note: ("patient_note", "Note"),
}


def event_import_key(client_entry_id: uuid.UUID) -> str:
    """Fold the client-minted entry id into the import key (ALCOA sweep #3): a retry of one
    compose action skips gracefully; two genuine same-day events (distinct ids) both
    persist."""
    return f"{SourceType.event.value}:{client_entry_id}"


def _date_to_datetime(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def event_to_observation(
    body: EventIn,
    *,
    patient_id: uuid.UUID,
    import_key: str,
    recorded_at: datetime,
) -> Observation:
    """Map one between-visit event/note to its append-only Observation row."""
    code, display = EVENT_CODES[body.type]
    return Observation(
        patient_id=patient_id,
        source=SourceType.event,
        origin=DataOrigin.patient_reported,
        code=code,
        code_system=None,
        value_num=None,
        value_text=body.note,
        unit=None,
        effective_at=_date_to_datetime(body.effective_date),
        recorded_at=recorded_at,
        status=ObservationStatus.final,
        revises_id=None,
        recorded_by_role="patient",
        import_key=import_key,
        quality={"human_confirmed": True},
        payload={"type": body.type.value, "display": display, "reviewed": False},
    )
