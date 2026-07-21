"""API schemas for patient-entered between-visit events & notes (ADR-0045 P2).

Each event is one APPEND-ONLY Observation row (source=event): a short, dated record of
something that happened between visits — a fall, an ER visit, a new provider, a
hospitalization, a new supplement, or a free-text note. The note is the patient's own
words: PHI, never fed to AI narration, audited by count/ref only.

This surface does NO red-flag scanning or triage — the note channel is not monitored in
real time (the persistent emergency banner lives on the capture UI, frontend). All data is
patient-entered (`origin=patient_reported`).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.base import ApiModel

# Note length matches the Observation `value_text` cap (ADR "free-text note, short").
EVENT_NOTE_MAX = 500


class EventType(StrEnum):
    """The closed vocabulary of between-visit events (plus a plain note)."""

    fall = "fall"
    er_visit = "er_visit"
    new_provider = "new_provider"
    hospitalization = "hospitalization"
    new_supplement = "new_supplement"
    note = "note"


class EventIn(ApiModel):
    """Record one between-visit event or note (ADR-0045 P2)."""

    type: EventType
    effective_date: date = Field(..., description="The date the event happened")
    note: str | None = Field(
        default=None,
        max_length=EVENT_NOTE_MAX,
        description="Optional short note (the patient's own words)",
    )
    client_entry_id: UUID = Field(
        ..., description="Client-minted idempotency id — a retry of one compose action skips"
    )

    @model_validator(mode="after")
    def _note_requires_text(self) -> EventIn:
        # A `note` event with no note records nothing — reject it (422). Every other type
        # allows an optional note.
        if self.type is EventType.note and not (self.note and self.note.strip()):
            raise ValueError("a note event needs a non-empty note")
        return self


class EventOut(BaseModel):
    """One recorded event. `skipped` is True on an idempotent retry (client_entry_id
    already on file), so no new row was written."""

    event_id: UUID
    type: EventType
    effective_at: datetime
    note: str | None
    reviewed: bool
    skipped: bool


class EventList(BaseModel):
    """The patient's between-visit events & notes, newest-first."""

    items: list[EventOut] = Field(default_factory=list)
