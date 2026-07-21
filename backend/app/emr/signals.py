"""EMR pull signals — existence-only events emitted on the persist path (ADR-0045 P2 #27).

``NewChartNoteSignal`` announces that a NEW clinical note landed for a patient. It carries
the note's EXISTENCE + METADATA only (id, type, author, date, encounter reference) — NO
body, no interpretation. It is the data source for the caregiver "New chart note after a
visit" alert (ADR-0047, task #27), whose consumer is out of scope here: this build only
EMITS the signal into an injectable sink, AFTER the whole batch (rows + audit event) has
persisted, for the idempotent ``add_if_absent`` -> True inserts only — so a re-pull of the
same note never re-alerts and a failed persist never emits a phantom alert. A true
post-COMMIT hook/outbox is out of scope (the request transaction commits above this
layer); the residual window is absorbed by consumers deduping on the signal's stable
``import_key``.

The sink is a Protocol with an in-memory default, mirroring the audit/secret_store
injection idiom on ``EmrService`` — a real fan-out (queue/push) swaps the implementation
without touching the pull flow.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class NewChartNoteSignal:
    """A new clinical note exists — metadata only, never the note body or any reading.

    ``import_key`` is the note's STABLE identity (source-scoped DocumentReference key):
    ``note_id`` is a fresh row UUID that changes if a rolled-back import retries, so
    consumers MUST dedupe on ``(patient_id, import_key)``, never on ``note_id``.
    """

    patient_id: uuid.UUID
    connection_id: uuid.UUID
    note_id: uuid.UUID
    import_key: str
    type_display: str | None
    author_display: str | None
    authored_at: datetime
    encounter_fhir_id: str | None


class NewChartNoteSink(Protocol):
    """Where a NewChartNoteSignal goes when a new note is persisted."""

    async def emit(self, signal: NewChartNoteSignal) -> None: ...


class InMemoryNewChartNoteSink:
    """List-backed sink for unit tests and DB-less development (the caregiver consumer,
    ADR-0047, is out of scope — this just records the emitted signals)."""

    def __init__(self) -> None:
        self.signals: list[NewChartNoteSignal] = []

    async def emit(self, signal: NewChartNoteSignal) -> None:
        self.signals.append(signal)
