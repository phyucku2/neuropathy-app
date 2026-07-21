"""EMR clinical-note repository — interface + in-memory implementation (ADR-0045 P2 #27).

Works directly with the append-only ``models.EmrClinicalNote`` row. Mirrors the
observation repository's idempotent-write contract (``add_if_absent`` +
``existing_import_keys``): the pre-write batch probe narrows the common case, and the
DB-level partial UNIQUE index (``uq_emr_note_patient_import_key``) is the real invariant
that ``add_if_absent`` absorbs as a skip rather than a 500 under a concurrent re-pull.

Reads carry only the note's metadata — never body text, which is not a column at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.models.emr_clinical_note import EmrClinicalNote


def _aware(value: datetime) -> datetime:
    """Treat a naive stored timestamp as UTC (defense in depth on the read path)."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class EmrClinicalNoteRepository(Protocol):
    """Persistence contract for a patient's pulled clinical notes (metadata only)."""

    async def add_if_absent(self, note: EmrClinicalNote) -> bool:
        """Idempotent insert keyed on (patient_id, import_key): persist unless a note with
        the same import_key already exists for the patient. Returns True if this call
        inserted, False if a matching note was already on file.

        The pre-write ``existing_import_keys`` probe narrows the common case, but a
        concurrent pull can commit between that probe and this write — the DB partial-unique
        index makes the duplicate impossible and this returns False rather than raising."""
        ...

    async def existing_import_keys(self, patient_id: uuid.UUID, import_keys: list[str]) -> set[str]:
        """The subset of `import_keys` already on file — ONE probe per batch, not N."""
        ...

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        *,
        since: datetime | None = None,
        newest_first: bool = False,
    ) -> list[EmrClinicalNote]:
        """One patient's notes, ordered by authored_at (oldest first by default). `since`
        bounds the lookback by authored_at (the visit-summary window read)."""
        ...

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        """Destroy every clinical-note row for one patient (ADR-0027). Callers own the FK
        order: this runs BEFORE emr_connections.delete_for_patient (notes FK the connection).
        """
        ...


class InMemoryEmrClinicalNoteRepository:
    """List-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._notes: list[EmrClinicalNote] = []

    async def add_if_absent(self, note: EmrClinicalNote) -> bool:
        # Mirror the DB partial-unique index: uniqueness on (patient_id, import_key) only
        # when import_key is set (a null key never collides).
        if note.import_key is not None and any(
            n.patient_id == note.patient_id and n.import_key == note.import_key for n in self._notes
        ):
            return False
        if note.id is None:
            note.id = uuid.uuid4()  # column default only applies on DB flush; mirror it
        self._notes.append(note)
        return True

    async def existing_import_keys(self, patient_id: uuid.UUID, import_keys: list[str]) -> set[str]:
        wanted = set(import_keys)
        return {
            n.import_key
            for n in self._notes
            if n.patient_id == patient_id and n.import_key in wanted and n.import_key is not None
        }

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        *,
        since: datetime | None = None,
        newest_first: bool = False,
    ) -> list[EmrClinicalNote]:
        rows = [
            n
            for n in self._notes
            if n.patient_id == patient_id and (since is None or _aware(n.authored_at) >= since)
        ]
        rows.sort(key=lambda n: _aware(n.authored_at), reverse=newest_first)
        return rows

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        self._notes = [n for n in self._notes if n.patient_id != patient_id]
