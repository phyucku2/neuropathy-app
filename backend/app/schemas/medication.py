"""API schemas for the patient-entered medication & supplement change log (ADR-0045 P2).

The medication log is APPEND-ONLY: registering a drug emits one `added` change entry, and
every later dose change or stop is its OWN new entry (never an overwrite) — the full set of
a medication's entries IS its history. A dose change is history, not a correction; the
Observation `revises_id` correction path is reserved for fixing a mistaken entry.

This surface is a LIST the patient keeps: it never adjusts, checks, interacts, or
recommends anything (the hard non-diagnostic line, CLAUDE.md). Free-text (name, prescriber,
reason) is PHI. All data is patient-entered (`origin=patient_reported`).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.base import ApiModel


class MedicationKind(StrEnum):
    """What kind of thing this is — a prescription, an over-the-counter drug, or a
    supplement. Closed vocabulary so the log never carries free-text categories."""

    prescription = "prescription"
    otc = "otc"
    supplement = "supplement"


class MedicationChangeType(StrEnum):
    """The kind of change entry. `added` is minted at registration; `dose_changed` and
    `stopped` are appended later. None supersedes another — the set is the history."""

    added = "added"
    dose_changed = "dose_changed"
    stopped = "stopped"


class MedicationStatus(StrEnum):
    """Current folded state of a medication: still taken, or stopped. A stopped med is
    still shown (never dropped) — the log endures."""

    active = "active"
    stopped = "stopped"


class MedicationRegisterIn(ApiModel):
    """Register a NEW medication/supplement — emits the `added` change entry (ADR-0045 P2)."""

    name: str = Field(..., min_length=1, max_length=200, description="Drug/supplement name")
    kind: MedicationKind
    dose_amount: float | None = Field(default=None, description="Numeric dose amount, e.g. 50")
    dose_unit: str | None = Field(default=None, max_length=40, description="Dose unit, e.g. mg")
    dose_text: str | None = Field(
        default=None, max_length=200, description="Free-text dose, e.g. '1 tablet twice daily'"
    )
    prescriber: str | None = Field(default=None, max_length=200, description="Who prescribed it")
    reason: str | None = Field(default=None, max_length=500, description="Why (optional)")
    started_on: date = Field(..., description="The date this medication was started")
    client_entry_id: UUID = Field(
        ..., description="Client-minted idempotency id — a retry of one compose action skips"
    )


class MedicationChangeIn(ApiModel):
    """Append a dose change or a stop to an existing medication's log (ADR-0045 P2)."""

    change_type: MedicationChangeType = Field(
        ..., description="dose_changed or stopped (a new `added` uses POST /medications)"
    )
    dose_amount: float | None = Field(default=None)
    dose_unit: str | None = Field(default=None, max_length=40)
    dose_text: str | None = Field(default=None, max_length=200)
    reason: str | None = Field(default=None, max_length=500)
    effective_date: date = Field(..., description="The date the change took effect")
    client_entry_id: UUID = Field(..., description="Client-minted idempotency id")

    @model_validator(mode="after")
    def _dose_change_carries_a_dose(self) -> MedicationChangeIn:
        # A dose_changed entry with no dose at all records nothing — reject it (422). A
        # `stopped` entry needs no dose. Registration (`added`) is a different schema.
        if self.change_type is MedicationChangeType.dose_changed and (
            self.dose_amount is None and self.dose_unit is None and self.dose_text is None
        ):
            raise ValueError("dose_changed needs at least one of dose_amount, dose_unit, dose_text")
        if self.change_type is MedicationChangeType.added:
            raise ValueError("use POST /medications to add a new medication")
        return self


class MedicationChangeOut(BaseModel):
    """One appended change entry's outcome. `skipped` is True when the client_entry_id
    was already on file (an idempotent retry), so no new row was written."""

    medication_id: str
    change_type: MedicationChangeType
    effective_at: datetime
    skipped: bool


class MedicationChangeEntry(BaseModel):
    """One entry in a medication's append-only change log (oldest→newest is the history)."""

    change_type: MedicationChangeType
    effective_at: datetime
    dose_amount: float | None
    dose_unit: str | None
    dose_text: str | None
    reason: str | None


class MedicationOut(BaseModel):
    """A medication folded to its current state, plus its full change log (ADR-0045 P2)."""

    medication_id: str
    name: str
    kind: MedicationKind
    status: MedicationStatus
    current_dose_amount: float | None
    current_dose_unit: str | None
    current_dose_text: str | None
    prescriber: str | None
    started_on: date
    last_change_at: datetime
    changes: list[MedicationChangeEntry] = Field(default_factory=list)


class MedicationLog(BaseModel):
    """The patient's folded current medication list + per-med change log, active-first."""

    items: list[MedicationOut] = Field(default_factory=list)
